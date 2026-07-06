import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ToolHandler = Callable[[dict, "ExecutionContext"], Any]
ContextManager = Callable[[list], list]
AssistantCallback = Callable[[str], None]
PrintCallback = Callable[..., None]


@dataclass(frozen=True)
class ExecutionContext:
    mode: str = "interactive"
    allowed_root: str | None = None
    default_recipient: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    properties: dict
    required: list[str]
    handler: ToolHandler

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": self.required,
                },
            },
        }


class ToolPolicy:
    def __init__(self):
        self.autonomous_blocked_tools = {"test_code", "schedule_task"}

    def _normalize_under_root(self, target_path: str, allowed_root: str) -> str:
        normalized_root = os.path.abspath(os.path.normpath(allowed_root))
        if os.path.isabs(target_path):
            return os.path.abspath(os.path.normpath(target_path))
        return os.path.abspath(os.path.normpath(os.path.join(normalized_root, target_path)))

    def _ensure_inside_root(self, target_path: str, allowed_root: str) -> bool:
        if not target_path:
            return False
        normalized_root = os.path.abspath(os.path.normpath(allowed_root))
        normalized_target = self._normalize_under_root(target_path, allowed_root)
        try:
            return os.path.commonpath([normalized_root, normalized_target]) == normalized_root
        except ValueError:
            return False

    def _inject_defaults(self, tool_name: str, args: dict, ctx: ExecutionContext) -> dict:
        normalized = dict(args or {})
        if tool_name == "send_report_email" and not normalized.get("to") and ctx.default_recipient:
            normalized["to"] = ctx.default_recipient
        return normalized

    def _validate_required(self, tool: ToolDefinition, args: dict):
        missing = [field for field in tool.required if args.get(field) in (None, "")]
        if missing:
            raise ValueError(f"Brak wymaganych argumentow: {', '.join(missing)}")

    def enforce(self, tool: ToolDefinition, args: dict, ctx: ExecutionContext) -> dict:
        normalized = self._inject_defaults(tool.name, args, ctx)
        self._validate_required(tool, normalized)

        if ctx.mode != "autonomous":
            return normalized

        if tool.name in self.autonomous_blocked_tools:
            raise PermissionError(f"Narzędzie {tool.name} jest zablokowane w trybie autonomicznym.")

        if tool.name in {"write_file", "read_file", "list_dir"}:
            allowed_root = ctx.allowed_root
            if not allowed_root:
                raise PermissionError("Brak configured allowed_root dla trybu autonomicznego.")
            path = normalized.get("path", ".")
            if not self._ensure_inside_root(path, allowed_root):
                raise PermissionError(f"Dostep poza dozwolony katalog: {path}")
            normalized["path"] = self._normalize_under_root(path, allowed_root)

        if tool.name == "send_report_email":
            to_email = str(normalized.get("to", "")).lower()
            default_recipient = str(ctx.default_recipient or "").lower()
            if not default_recipient:
                raise PermissionError("Brak domyslnego recipient dla trybu autonomicznego.")
            if to_email != default_recipient:
                raise PermissionError("Autonomia moze wysylac maile tylko do domyslnego odbiorcy.")

        return normalized


class ToolRegistry:
    def __init__(self, policy: ToolPolicy | None = None):
        self.policy = policy or ToolPolicy()
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def to_openai_tools(self) -> list[dict]:
        return [tool.to_openai_tool() for tool in self._tools.values()]

    def execute(self, name: str, args: dict, ctx: ExecutionContext) -> Any:
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Nieznane narzedzie: {name}")
        normalized_args = self.policy.enforce(tool, args or {}, ctx)
        return tool.handler(normalized_args, ctx)


def build_execution_plan(user_text: str) -> list[str]:
    text = (user_text or "").lower()
    plan = ["Zrozumiec cel i ograniczenia", "Dobrac narzedzia i wykonac akcje", "Zweryfikowac wynik i odpowiedziec"]

    if any(token in text for token in ["mail", "email", "poczta"]):
        plan[1] = "Sprawdzic dane odbiorcy i wykonac akcje mailowe"
    elif any(token in text for token in ["plik", "file", "zapisz", "odczytaj"]):
        plan[1] = "Przeanalizowac operacje plikowe i wykonac je bezpiecznie"
    elif any(token in text for token in ["kalendarz", "calendar", "spotkanie"]):
        plan[1] = "Wywolac narzedzia kalendarza i potwierdzic rezultat"

    return plan


class AgentExecutor:
    def run_loop(
        self,
        *,
        history: list,
        llm_client: Any,
        model_name: str,
        tools_schema: list[dict],
        execute_tool: Callable[[str, dict, str], Any],
        mode: str = "interactive",
        print_callback: PrintCallback | None = None,
        on_assistant_content: AssistantCallback | None = None,
        context_manager: ContextManager | None = None,
    ) -> list:
        announced_plan = False
        rounds = 0
        max_rounds = 24
        while True:
            rounds += 1
            if rounds > max_rounds:
                if print_callback:
                    print_callback("[!] Przerwano petle narzedzi (limit iteracji).", is_status=True)
                break
            if context_manager:
                history = context_manager(history)

            if not announced_plan and print_callback:
                user_message = None
                for msg in reversed(history):
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        user_message = msg.get("content", "")
                        break
                if user_message:
                    plan = build_execution_plan(str(user_message))
                    print_callback(f"[*] Plan: {' -> '.join(plan)}", is_status=True)
                    announced_plan = True

            response = None
            last_error = None
            for attempt in range(3):
                try:
                    response = llm_client.chat.completions.create(
                        model=model_name, messages=history, tools=tools_schema
                    )
                    break
                except Exception as e:
                    last_error = e
                    time.sleep(2 ** attempt)
            if response is None:
                raise last_error
            msg = response.choices[0].message
            history.append(msg)

            if getattr(msg, "content", None):
                content = msg.content
                if print_callback:
                    print_callback(content)
                if on_assistant_content:
                    on_assistant_content(content)

            if not getattr(msg, "tool_calls", None):
                break

            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except Exception:
                    args = {}

                if print_callback:
                    print_callback(f"[*] Piorun aktywuje: {name}", is_status=True)

                result = execute_tool(name, args, mode)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": name,
                        "content": str(result),
                    }
                )
        return history
