from types import SimpleNamespace

import pytest

import core.agent_runtime as rt


def _tool(name="write_file", required=None):
    return rt.ToolDefinition(
        name=name,
        description="t",
        properties={},
        required=required or [],
        handler=lambda args, ctx: "ok",
    )


def _ctx(mode="autonomous", root=None, recipient="mateusz@example.com"):
    return rt.ExecutionContext(mode=mode, allowed_root=root, default_recipient=recipient)


class TestToolPolicy:
    def test_blocks_path_escape_in_autonomous_mode(self, tmp_path):
        policy = rt.ToolPolicy()
        with pytest.raises(PermissionError):
            policy.enforce(_tool(), {"path": "..\\..\\evil.txt"}, _ctx(root=str(tmp_path)))
        with pytest.raises(PermissionError):
            policy.enforce(_tool(), {"path": "C:\\Windows\\system32\\x.txt"}, _ctx(root=str(tmp_path)))

    def test_allows_path_inside_root(self, tmp_path):
        policy = rt.ToolPolicy()
        result = policy.enforce(_tool(), {"path": "notatka.md"}, _ctx(root=str(tmp_path)))
        assert result["path"].startswith(str(tmp_path))

    def test_interactive_mode_is_not_restricted(self, tmp_path):
        policy = rt.ToolPolicy()
        result = policy.enforce(
            _tool(), {"path": "C:\\gdziekolwiek\\plik.txt"}, _ctx(mode="interactive", root=str(tmp_path))
        )
        assert result["path"] == "C:\\gdziekolwiek\\plik.txt"

    def test_blocks_dangerous_tools_in_autonomous_mode(self):
        policy = rt.ToolPolicy()
        with pytest.raises(PermissionError):
            policy.enforce(_tool(name="test_code"), {}, _ctx())

    def test_email_only_to_default_recipient(self):
        policy = rt.ToolPolicy()
        with pytest.raises(PermissionError):
            policy.enforce(
                _tool(name="send_report_email"),
                {"to": "obcy@example.com"},
                _ctx(),
            )
        result = policy.enforce(
            _tool(name="send_report_email"),
            {"to": "mateusz@example.com"},
            _ctx(),
        )
        assert result["to"] == "mateusz@example.com"

    def test_missing_required_args_raise(self):
        policy = rt.ToolPolicy()
        with pytest.raises(ValueError):
            policy.enforce(_tool(required=["path"]), {}, _ctx(mode="interactive"))


def _assistant_message(content="odpowiedz", tool_calls=None):
    return SimpleNamespace(role="assistant", content=content, tool_calls=tool_calls)


def _response(msg):
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FlakyClient:
    """Pada dwa razy, za trzecim zwraca poprawna odpowiedz."""

    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        if self.calls < 3:
            raise ConnectionError("transient 503")
        return _response(_assistant_message())


class _LoopingClient:
    """Zawsze kaze wywolac narzedzie - test limitu iteracji."""

    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        tool_call = SimpleNamespace(
            id=f"tc_{self.calls}",
            function=SimpleNamespace(name="web_search", arguments="{}"),
        )
        return _response(_assistant_message(content=None, tool_calls=[tool_call]))


def test_run_loop_retries_transient_llm_errors(monkeypatch):
    monkeypatch.setattr(rt.time, "sleep", lambda _s: None)
    client = _FlakyClient()
    history = rt.AgentExecutor().run_loop(
        history=[{"role": "user", "content": "czesc"}],
        llm_client=client,
        model_name="m",
        tools_schema=[],
        execute_tool=lambda name, args, mode: "ok",
    )
    assert client.calls == 3
    assert getattr(history[-1], "content", None) == "odpowiedz"


def test_run_loop_stops_at_max_rounds(monkeypatch):
    monkeypatch.setattr(rt.time, "sleep", lambda _s: None)
    client = _LoopingClient()
    rt.AgentExecutor().run_loop(
        history=[{"role": "user", "content": "petla"}],
        llm_client=client,
        model_name="m",
        tools_schema=[],
        execute_tool=lambda name, args, mode: "ok",
    )
    assert client.calls == 24
