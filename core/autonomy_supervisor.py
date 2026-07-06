import json
import os
import re
import threading
import time
import hashlib
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.config import get_settings
import tools.memory as memory

SETTINGS = get_settings()

DECISIONS_PATH = SETTINGS.autonomy_state_dir / "decisions.jsonl"
QUEUE_PATH = SETTINGS.autonomy_state_dir / "queue.json"
STATE_PATH = SETTINGS.autonomy_state_dir / "state.json"
IO_LOCK = threading.RLock()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _clip_text(value: str, max_len: int) -> str:
    text = str(value or "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _read_json(path: Path, default):
    with IO_LOCK:
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default


def _write_json(path: Path, payload):
    with IO_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def _append_jsonl(path: Path, payload):
    with IO_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _daily_log_path() -> Path:
    logs_dir = SETTINGS.allowed_root / "autonomy_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"


def _append_daily_log_lines(lines: list[str]):
    if not lines:
        return
    path = _daily_log_path()
    with IO_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line.rstrip() + "\n")
            f.write("\n")


def _extract_json_blob(text: str):
    raw = (text or "").strip()
    if not raw:
        return "{}"
    raw = raw.replace("```json", "```")
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        return match.group(0)
    return raw


def _load_state():
    state = _read_json(STATE_PATH, {})
    hour_bucket = datetime.now().strftime("%Y-%m-%d-%H")
    if state.get("hour_bucket") != hour_bucket:
        state["hour_bucket"] = hour_bucket
        state["autoexec_count"] = 0
    state.setdefault("autoexec_count", 0)
    state.setdefault("ticks_count", 0)
    state.setdefault("last_tick_at", "")
    return state


def _save_state(state):
    _write_json(STATE_PATH, state)


def _load_queue():
    queue = _read_json(QUEUE_PATH, [])
    return queue if isinstance(queue, list) else []


def _save_queue(queue_items):
    _write_json(QUEUE_PATH, queue_items)


def _enqueue(item):
    with IO_LOCK:
        queue_items = _read_json(QUEUE_PATH, [])
        queue_items = queue_items if isinstance(queue_items, list) else []
        deduped, changed = _dedupe_queue_items(queue_items)
        if changed:
            queue_items = deduped
        new_fp = _ensure_item_fingerprint(item) if isinstance(item, dict) else ""
        new_semantic = _ensure_item_semantic_key(item) if isinstance(item, dict) else ""
        if new_fp:
            for existing in queue_items:
                existing_fp = _ensure_item_fingerprint(existing)
                existing_semantic = _ensure_item_semantic_key(existing)
                if existing_fp == new_fp or (new_semantic and existing_semantic == new_semantic):
                    return {"added": False, "id": str(existing.get("id", "")), "reason": "duplicate_pending_queue"}
        queue_items.append(item)
        queue_items = queue_items[-100:]
        _write_json(QUEUE_PATH, queue_items)
        return {"added": True, "id": str(item.get("id", ""))}


def _make_queue_id():
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"AQ_{ts}_{os.getpid()}_{threading.get_ident()}"


def _normalize_confidence(value: Any) -> int:
    return max(0, min(100, _safe_int(value, 0)))


def _normalize_risk(value: Any) -> str:
    risk = str(value or "").strip().lower()
    if risk in {"low", "medium", "high"}:
        return risk
    return "high"


def _sanitize_text(value: Any, max_len: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _sanitize_action(action: dict) -> dict:
    if not isinstance(action, dict):
        return {}
    action_type = str(action.get("type", "")).strip().lower()
    if action_type == "web_search":
        query = _sanitize_text(action.get("query", ""), 300)
        return {"type": "web_search", "query": query} if query else {}
    if action_type == "write_note":
        title = _sanitize_text(action.get("title", "Autonomy Note"), 160) or "Autonomy Note"
        content = _sanitize_text(action.get("content", ""), 4000)
        return {"type": "write_note", "title": title, "content": content} if content else {}
    return {}


def _sanitize_proposal(raw: dict) -> dict:
    proposal = raw if isinstance(raw, dict) else {}
    return {
        "title": _sanitize_text(proposal.get("title", ""), 200),
        "reason": _sanitize_text(proposal.get("reason", ""), 1000),
        "risk": _normalize_risk(proposal.get("risk", "high")),
        "confidence": _normalize_confidence(proposal.get("confidence", 0)),
        "action": _sanitize_action(proposal.get("action", {})),
    }


_STOPWORDS = {
    "and",
    "for",
    "the",
    "this",
    "that",
    "with",
    "or",
    "dla",
    "oraz",
    "jest",
    "to",
    "sie",
    "się",
    "czy",
    "or",
    "jak",
    "aby",
    "mateusz",
}

_TOPIC_AI = {"ai", "ml", "llm", "machine", "learning", "sztucznej", "inteligencji"}
_TOPIC_CYBER = {"cyber", "cyberbezpieczenstwo", "cyberbezpieczenstwa", "zagrozenia", "security", "luki"}
_TOPIC_LEARNING = {"kursy", "kurs", "nauki", "zasoby", "edukacyjnych", "tutoriale", "materialy"}
_TOPIC_TRENDS = {"trendy", "najnowsze", "aktualne", "news", "nowosci"}
_TOPIC_GOALS = {"cele", "celow", "krotkoterminowe", "dlugoterminowe", "priorytety", "profil"}
_TOPIC_HEARTBEAT = {"heartbeat", "autonomy", "kontrolny"}


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_tokens(text: Any, *, max_tokens: int = 18) -> str:
    raw = _sanitize_text(text, 2000).lower()
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    raw = re.sub(r"\b20\d{2}\b", " ", raw)
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    tokens: list[str] = []
    for token in raw.split():
        if (len(token) < 3 and token not in {"ai", "ml"}) or token in _STOPWORDS:
            continue
        tokens.append(token)
    unique = sorted(set(tokens))
    return " ".join(unique[:max_tokens])


def _action_fingerprint(action: dict) -> str:
    clean = _sanitize_action(action)
    action_type = str(clean.get("type", "")).lower().strip()
    if action_type == "web_search":
        token_key = _normalize_tokens(clean.get("query", ""), max_tokens=20)
        return f"web_search::{token_key}" if token_key else ""
    if action_type == "write_note":
        token_key = _normalize_tokens(
            f"{clean.get('title','')} {clean.get('content','')}",
            max_tokens=24,
        )
        if not token_key:
            return ""
        digest = hashlib.sha1(token_key.encode("utf-8")).hexdigest()[:12]
        return f"write_note::{digest}"
    return ""


def _semantic_flags(tokens: set[str]) -> list[str]:
    flags: list[str] = []
    if tokens & _TOPIC_AI:
        flags.append("ai")
    if tokens & _TOPIC_CYBER:
        flags.append("cyber")
    if tokens & _TOPIC_LEARNING:
        flags.append("learning")
    if tokens & _TOPIC_TRENDS:
        flags.append("trends")
    if tokens & _TOPIC_GOALS:
        flags.append("goals")
    if tokens & _TOPIC_HEARTBEAT:
        flags.append("heartbeat")
    return sorted(set(flags))


def _action_semantic_key(action: dict) -> str:
    clean = _sanitize_action(action)
    action_type = str(clean.get("type", "")).lower().strip()
    if action_type == "web_search":
        token_key = _normalize_tokens(clean.get("query", ""), max_tokens=30)
        tokens = set(token_key.split())
        flags = _semantic_flags(tokens)
        if flags:
            return f"web_search_topic::{'+'.join(flags)}"
        return f"web_search_topic::{'+'.join(sorted(list(tokens))[:4])}" if tokens else ""
    if action_type == "write_note":
        token_key = _normalize_tokens(
            f"{clean.get('title','')} {clean.get('content','')}",
            max_tokens=30,
        )
        tokens = set(token_key.split())
        flags = _semantic_flags(tokens)
        if flags:
            return f"write_note_topic::{'+'.join(flags)}"
        return f"write_note_topic::{'+'.join(sorted(list(tokens))[:4])}" if tokens else ""
    return ""


def _ensure_item_fingerprint(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    existing = _sanitize_text(item.get("fingerprint", ""), 120)
    if existing:
        return existing
    action = item.get("action", {}) if isinstance(item.get("action", {}), dict) else {}
    fp = _action_fingerprint(action)
    if fp:
        item["fingerprint"] = fp
    return fp


def _ensure_item_semantic_key(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    existing = _sanitize_text(item.get("semantic_key", ""), 120)
    if existing:
        return existing
    action = item.get("action", {}) if isinstance(item.get("action", {}), dict) else {}
    semantic = _action_semantic_key(action)
    if semantic:
        item["semantic_key"] = semantic
    return semantic


def _dedupe_queue_items(queue_items: list[dict]) -> tuple[list[dict], bool]:
    if not queue_items:
        return [], False
    seen: set[str] = set()
    deduped: list[dict] = []
    changed = False
    for item in queue_items:
        if not isinstance(item, dict):
            changed = True
            continue
        fp = _ensure_item_fingerprint(item)
        semantic = _ensure_item_semantic_key(item)
        dedupe_key = semantic or fp
        if dedupe_key:
            if dedupe_key in seen:
                changed = True
                continue
            seen.add(dedupe_key)
        deduped.append(item)
    return deduped, changed


def _prune_recent_actions(state: dict) -> list[dict]:
    raw_entries = state.get("recent_actions", [])
    if not isinstance(raw_entries, list):
        raw_entries = []
    now = datetime.now(timezone.utc)
    ttl_minutes = max(
        30,
        int(SETTINGS.autonomy_action_cooldown_minutes) * 4,
        int(SETTINGS.autonomy_heartbeat_cooldown_minutes) * 2,
    )
    cutoff = now - timedelta(minutes=ttl_minutes)
    cleaned: list[dict] = []
    for item in raw_entries[-400:]:
        if not isinstance(item, dict):
            continue
        fp = _sanitize_text(item.get("fingerprint", ""), 120)
        at = _parse_iso(item.get("at"))
        if not fp or at is None:
            continue
        if at < cutoff:
            continue
        action_type = _sanitize_text(item.get("action_type", ""), 30)
        title = _sanitize_text(item.get("title", ""), 200)
        semantic_key = _sanitize_text(item.get("semantic_key", ""), 120)
        if not semantic_key and action_type == "web_search":
            semantic_key = _action_semantic_key({"type": "web_search", "query": title})
        elif not semantic_key and action_type == "write_note":
            semantic_key = _action_semantic_key({"type": "write_note", "title": title, "content": title})
        cleaned.append(
            {
                "at": at.isoformat(),
                "fingerprint": fp,
                "semantic_key": semantic_key,
                "action_type": action_type,
                "title": title,
                "source": _sanitize_text(item.get("source", ""), 40),
            }
        )
    state["recent_actions"] = cleaned[-200:]
    return state["recent_actions"]


def _remember_action(state: dict, action: dict, title: str, source: str) -> str:
    fp = _action_fingerprint(action)
    if not fp:
        return ""
    semantic_key = _action_semantic_key(action)
    entries = _prune_recent_actions(state)
    entries.append(
        {
            "at": _now_iso(),
            "fingerprint": fp,
            "semantic_key": semantic_key,
            "action_type": _sanitize_text(action.get("type", ""), 30),
            "title": _sanitize_text(title, 200),
            "source": _sanitize_text(source, 40),
        }
    )
    state["recent_actions"] = entries[-200:]
    return fp


def _cooldown_minutes_for_action(action: dict, title: str = "") -> int:
    merged = f"{title} {action.get('title','')} {action.get('content','')}"
    if "heartbeat" in merged.lower():
        return max(1, int(SETTINGS.autonomy_heartbeat_cooldown_minutes))
    return max(1, int(SETTINGS.autonomy_action_cooldown_minutes))


def _is_action_recent_duplicate(state: dict, action: dict, title: str = "") -> bool:
    fp = _action_fingerprint(action)
    semantic_key = _action_semantic_key(action)
    if not fp and not semantic_key:
        return False
    entries = _prune_recent_actions(state)
    cooldown = _cooldown_minutes_for_action(action, title=title)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown)
    for item in reversed(entries):
        matches_fp = bool(fp and item.get("fingerprint") == fp)
        matches_semantic = bool(semantic_key and item.get("semantic_key") == semantic_key)
        if not (matches_fp or matches_semantic):
            continue
        at = _parse_iso(item.get("at"))
        if at is not None and at >= cutoff:
            return True
    return False


def _recent_actions_prompt_block(state: dict, limit: int = 10) -> str:
    entries = _prune_recent_actions(state)
    if not entries:
        return "- Brak."
    lines = []
    for item in entries[-int(limit) :]:
        ts = str(item.get("at", ""))[-14:-6]
        lines.append(
            f"- {ts} | {item.get('action_type','')} | {item.get('title','')}"
        )
    return "\n".join(lines) if lines else "- Brak."


def _pending_queue_prompt_block(queue_items: list[dict], limit: int = 10) -> str:
    if not queue_items:
        return "- Brak."
    deduped, _ = _dedupe_queue_items(queue_items)
    lines = []
    for item in deduped[-int(limit) :]:
        lines.append(
            f"- {item.get('title','')} | {str(item.get('reason_blocked','')).lower()}"
        )
    return "\n".join(lines) if lines else "- Brak."


def _study_deadlines_prompt_block(limit: int = 8) -> str:
    try:
        import tools.study_deadlines as study

        plan = study.week_plan()
    except Exception:
        return "- Brak danych o terminach."
    if not plan:
        return "- Brak terminow w najblizszych 7 dniach."
    lines = []
    for item in plan[:int(limit)]:
        lines.append(
            f"- ({item.get('priority','')}) {item.get('due_at','')[:16]} | "
            f"{item.get('subject','')} | {item.get('title','')}"
        )
    return "\n".join(lines)


def _build_context(state: dict, queue_items: list[dict]):
    profile = ""
    profile_path = SETTINGS.workspace_root / "user_profile.md"
    if profile_path.exists():
        try:
            profile = profile_path.read_text(encoding="utf-8")
        except Exception:
            profile = ""
    profile = _clip_text(profile, 5000)

    summaries = memory.list_recent_session_summaries(limit=5)
    summary_lines = []
    for s in summaries:
        summary_lines.append(f"- {s.get('session_id')}: {_clip_text(s.get('summary_text', ''), 220)}")

    return {
        "profile": profile,
        "recent_summaries": "\n".join(summary_lines) if summary_lines else "- Brak podsumowan sesji.",
        "recent_autonomy_actions": _recent_actions_prompt_block(state, limit=12),
        "pending_queue_topics": _pending_queue_prompt_block(queue_items, limit=12),
        "study_deadlines": _study_deadlines_prompt_block(limit=8),
    }


def _parse_proposals_from_text(raw_text: str):
    blob = _extract_json_blob(raw_text or "")
    try:
        parsed = json.loads(blob)
    except Exception:
        parsed = {"thought": "parse_error", "proposals": []}
    if not isinstance(parsed, dict):
        parsed = {"thought": "parse_error_not_dict", "proposals": []}

    proposals_raw = parsed.get("proposals", [])
    if not isinstance(proposals_raw, list):
        proposals_raw = []

    normalized = []
    for raw in proposals_raw[:3]:
        proposal = _sanitize_proposal(raw)
        if proposal["action"]:
            normalized.append(proposal)
    return normalized


def _call_planner(prompt: str, max_tokens: int):
    import core.brain as brain

    response = brain.client.chat.completions.create(
        model=brain.MODEL_NAME,
        messages=[
            {"role": "system", "content": "Zwracasz tylko poprawny JSON bez komentarzy."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=max(120, int(max_tokens)),
        timeout=max(15, int(SETTINGS.autonomy_planner_timeout_seconds)),
    )
    msg = response.choices[0].message
    return getattr(msg, "content", "") or ""


def _propose_actions(state: dict, queue_items: list[dict]):
    context = _build_context(state=state, queue_items=queue_items)

    prompt = f"""
Jestes bezpiecznym planerem autonomii dla asystenta Mateusza.
Dzisiaj jest {datetime.now().strftime('%Y-%m-%d')}.
Zwracasz tylko JSON.
Masz podac 1 do 3 praktycznych propozycji, gdy user nic nie zlecil.
Dozwolone akcje:
- web_search: {{ "type": "web_search", "query": "..." }}
- write_note: {{ "type": "write_note", "title": "...", "content": "..." }}
WYMAGANIA:
- Nie powtarzaj semantycznie tych samych tematow, ktore byly wykonane niedawno albo sa juz w kolejce.
- Jesli temat byl juz poruszany, wybierz inny obszar lub bardziej konkretny nastepny krok.
- Zapytania web_search maja byc konkretne (temat + kontekst + biezacy rok, nie stare lata).
- content notatki write_note ma byc gotowa trescia (fakty, plan, checklist) - nigdy pytaniem do uzytkownika.
- Jesli sa nadchodzace terminy studenckie, preferuj akcje ktore realnie w nich pomagaja.

Kontekst profilu (skrot):
{context['profile']}

Nadchodzace terminy studenckie (7 dni):
{context['study_deadlines']}

Ostatnie podsumowania:
{context['recent_summaries']}

Ostatnio wykonane akcje autonomii (unikaj powtorek):
{context['recent_autonomy_actions']}

Tematy juz oczekujace w kolejce (nie dubluj):
{context['pending_queue_topics']}

Schema JSON:
{{
  "thought": "krotko",
  "proposals": [
    {{
      "title": "...",
      "reason": "...",
      "risk": "low|medium|high",
      "confidence": 0-100,
      "action": {{ "type": "web_search|write_note", "...": "..." }}
    }}
  ]
}}
"""

    planner_tokens = max(400, int(SETTINGS.autonomy_planner_max_tokens))
    content = _call_planner(prompt, max_tokens=planner_tokens)
    proposals = _parse_proposals_from_text(content)
    if proposals:
        return {"thought": "planner_primary", "proposals": proposals}

    fallback_prompt = """
Zwracaj tylko JSON.
Wygeneruj dokladnie 1 propozycje o niskim ryzyku.
Akcja ma byc write_note z krotkim planem dnia dla Mateusza.
Schema:
{
  "thought": "fallback",
  "proposals": [
    {
      "title": "...",
      "reason": "...",
      "risk": "low",
      "confidence": 80,
      "action": { "type": "write_note", "title": "...", "content": "..." }
    }
  ]
}
"""
    fallback_content = _call_planner(fallback_prompt, max_tokens=320)
    fallback_proposals = _parse_proposals_from_text(fallback_content)
    if fallback_proposals:
        return {"thought": "planner_fallback", "proposals": fallback_proposals}

    # Brak propozycji to poprawny wynik ticka - nie zasmiecamy notatek wpisami "heartbeat".
    return {"thought": "planner_no_proposals", "proposals": []}


def _append_note(title, content):
    notes_dir = SETTINGS.allowed_root / "autonomy_notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    note_path = notes_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    safe_title = _sanitize_text(title, 160).replace("\n", " ").replace("\r", " ").strip() or "Autonomy Note"
    with open(note_path, "a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.now().strftime('%H:%M:%S')} | {safe_title}\n")
        f.write(content.strip() + "\n")
    return str(note_path)


def _call_llm_text(prompt: str, max_tokens: int = 600) -> str:
    import core.brain as brain

    response = brain.client.chat.completions.create(
        model=brain.MODEL_NAME,
        messages=[
            {"role": "system", "content": "Piszesz zwiezle, konkretne notatki po polsku."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=max(120, int(max_tokens)),
        timeout=max(15, int(SETTINGS.autonomy_planner_timeout_seconds)),
    )
    msg = response.choices[0].message
    return (getattr(msg, "content", "") or "").strip()


def _format_search_results(raw_result: str) -> str:
    try:
        parsed = json.loads(str(raw_result))
    except Exception:
        return ""
    if not isinstance(parsed, list):
        return ""
    lines = []
    for item in parsed[:5]:
        if not isinstance(item, dict):
            continue
        title = _sanitize_text(item.get("title", ""), 160)
        body = _sanitize_text(item.get("body", ""), 400)
        href = _sanitize_text(item.get("href", ""), 300)
        if not (title or body):
            continue
        lines.append(f"- **{title}**\n  {body}\n  Zrodlo: {href}")
    return "\n".join(lines)


def _execute_low_risk_action(action):
    import core.brain as brain

    action_type = str(action.get("type", "")).lower().strip()
    if action_type == "web_search":
        query = str(action.get("query", "")).strip()
        if not query:
            return {"ok": False, "result": "Brak query"}
        res = brain.execute_tool_by_name("web_search", {"query": query}, mode="autonomous")
        formatted = _format_search_results(str(res))
        if not formatted:
            return {"ok": False, "result": f"web_search bez uzytecznych wynikow: {_clip_text(str(res), 200)}"}
        note_body = formatted
        try:
            synthesis = _call_llm_text(
                "Na podstawie ponizszych wynikow wyszukiwania napisz zwiezla notatke: "
                "3-6 punktow z konkretnymi faktami, na koncu sekcja 'Zrodla' z adresami URL. "
                f"Temat: {query}\n\nWyniki:\n{formatted}"
            )
            if len(synthesis) >= 100:
                note_body = f"{synthesis}\n\n---\nSurowe wyniki:\n{formatted}"
        except Exception:
            pass
        note_path = _append_note(f"Autonomy Research: {query}", note_body)
        return {"ok": True, "result": f"web_search wykonane, note: {note_path}"}
    if action_type == "write_note":
        title = str(action.get("title", "Autonomy Note")).strip() or "Autonomy Note"
        content = str(action.get("content", "")).strip()
        if not content:
            return {"ok": False, "result": "Brak content dla write_note"}
        note_path = _append_note(title, content)
        return {"ok": True, "result": f"write_note zapisane: {note_path}"}
    return {"ok": False, "result": f"Nieobslugiwany typ akcji: {action_type}"}


def _proposal_to_queue_item(proposal, reason):
    clean = _sanitize_proposal(proposal)
    return {
        "id": _make_queue_id(),
        "created_at": _now_iso(),
        "status": "PENDING_APPROVAL",
        "reason_blocked": reason,
        "title": clean["title"],
        "reason": clean["reason"],
        "risk": clean["risk"],
        "confidence": clean["confidence"],
        "action": clean["action"],
        "fingerprint": _action_fingerprint(clean["action"]),
        "semantic_key": _action_semantic_key(clean["action"]),
    }


def _pop_queue_item(item_id: str):
    with IO_LOCK:
        queue_items = _read_json(QUEUE_PATH, [])
        queue_items = queue_items if isinstance(queue_items, list) else []
        idx = None
        for i, item in enumerate(queue_items):
            if str(item.get("id", "")).strip() == str(item_id).strip():
                idx = i
                break
        if idx is None:
            return None
        item = queue_items.pop(idx)
        _write_json(QUEUE_PATH, queue_items)
        return item


def _drain_auto_queue(state: dict, event: dict, web_count: int, exec_budget: int):
    """
    Probujemy automatycznie wykonac pozycje, ktore byly odlozone tylko przez limity wykonania.
    """
    queue_items = _load_queue()
    if not queue_items:
        return web_count, 0

    queue_items, queue_changed = _dedupe_queue_items(queue_items)

    autoexec_limit = SETTINGS.autonomy_max_autoexec_per_hour
    confidence_threshold = SETTINGS.autonomy_min_confidence
    remaining = []
    changed = bool(queue_changed)
    executed_count = 0

    for item in queue_items:
        if executed_count >= max(0, int(exec_budget)):
            remaining.append(item)
            continue

        action = item.get("action", {}) if isinstance(item.get("action", {}), dict) else {}
        action = _sanitize_action(action)
        risk = _normalize_risk(item.get("risk", "high"))
        confidence = _normalize_confidence(item.get("confidence", 0))
        reason_blocked = str(item.get("reason_blocked", "")).strip().lower()
        action_type = str(action.get("type", "")).lower()
        title = _sanitize_text(item.get("title", ""), 200)

        if _is_action_recent_duplicate(state, action, title=title):
            changed = True
            event["skipped"].append({"title": title, "reason": "recent_duplicate_in_queue"})
            continue

        eligible_reason = reason_blocked in {"hourly_autoexec_limit", "web_search_tick_limit", "tick_exec_budget_limit"}
        eligible = bool(action) and risk == "low" and confidence >= confidence_threshold and eligible_reason
        if not eligible:
            remaining.append(item)
            continue

        if _safe_int(state.get("autoexec_count"), 0) >= autoexec_limit:
            remaining.append(item)
            continue

        if action_type == "web_search" and web_count >= SETTINGS.autonomy_max_web_results_per_tick:
            remaining.append(item)
            continue

        result = _execute_low_risk_action(action)
        if result.get("ok"):
            state["autoexec_count"] = _safe_int(state.get("autoexec_count"), 0) + 1
            if action_type == "web_search":
                web_count += 1
            executed_count += 1
            _remember_action(state, action, title=title, source="deferred_queue")
            event["executed"].append(
                {
                    "title": title,
                    "action_type": action_type,
                    "result": str(result.get("result", "")),
                    "source": "deferred_queue",
                }
            )
            changed = True
        else:
            item["reason_blocked"] = f"execution_failed: {result.get('result')}"
            item["last_try_at"] = _now_iso()
            remaining.append(item)
            changed = True

    if changed:
        _save_queue(remaining)
    return web_count, executed_count


def autonomy_tick():
    """
    Jedna iteracja autonomii:
    - planuje propozycje,
    - automatycznie wykonuje tylko low-risk z wysoką pewnością,
    - resztę wrzuca do kolejki akceptacji.
    """
    state = _load_state()
    _prune_recent_actions(state)
    state["ticks_count"] = _safe_int(state.get("ticks_count"), 0) + 1
    state["last_tick_at"] = _now_iso()

    queue_items = _load_queue()
    queue_items, queue_changed = _dedupe_queue_items(queue_items)
    if queue_changed:
        _save_queue(queue_items)

    event = {
        "timestamp": _now_iso(),
        "kind": "tick",
        "thought": "",
        "proposals": [],
        "executed": [],
        "queued": [],
        "skipped": [],
        "errors": [],
    }
    try:
        plan = _propose_actions(state=state, queue_items=queue_items)
        proposals = plan.get("proposals", [])[:3]
        event["thought"] = str(plan.get("thought", ""))[:500]
        for p in proposals:
            clean = _sanitize_proposal(p)
            event["proposals"].append(
                {
                    "title": clean.get("title", ""),
                    "risk": clean.get("risk", ""),
                    "confidence": clean.get("confidence", 0),
                    "action_type": str(clean.get("action", {}).get("type", "")),
                    "reason": _sanitize_text(clean.get("reason", ""), 260),
                }
            )
    except Exception as e:
        event["errors"].append(f"planner_error: {e}")
        _append_jsonl(DECISIONS_PATH, event)
        _save_state(state)
        _append_daily_log_lines(
            [
                f"## {datetime.now().strftime('%H:%M:%S')} | Tick ERROR",
                f"- thought: {event.get('thought', '')}",
                f"- errors: {', '.join(event.get('errors', []))}",
            ]
        )
        return event

    autoexec_limit = SETTINGS.autonomy_max_autoexec_per_hour
    confidence_threshold = SETTINGS.autonomy_min_confidence
    tick_budget = max(1, int(SETTINGS.autonomy_max_autoexec_per_tick))
    web_count = 0
    executed_this_tick = 0

    # Najpierw odblokowujemy pozycje oczekujace, ktore mogly zostac wykonane.
    web_count, drained_count = _drain_auto_queue(
        state,
        event,
        web_count=web_count,
        exec_budget=tick_budget,
    )
    executed_this_tick += int(drained_count)

    queue_items = _load_queue()
    queue_items, queue_changed = _dedupe_queue_items(queue_items)
    if queue_changed:
        _save_queue(queue_items)
    pending_fingerprints: set[str] = set()
    pending_semantic_keys: set[str] = set()
    for item in queue_items:
        if not isinstance(item, dict):
            continue
        item_fp = _ensure_item_fingerprint(item)
        item_semantic = _ensure_item_semantic_key(item)
        if item_fp:
            pending_fingerprints.add(item_fp)
        if item_semantic:
            pending_semantic_keys.add(item_semantic)

    for proposal in proposals:
        clean = _sanitize_proposal(proposal)
        risk = clean["risk"]
        confidence = clean["confidence"]
        action = clean["action"]
        action_type = str(action.get("type", "")).lower()
        title = clean["title"]
        fp = _action_fingerprint(action)
        semantic_key = _action_semantic_key(action)

        if (fp and fp in pending_fingerprints) or (
            semantic_key and semantic_key in pending_semantic_keys
        ):
            event["skipped"].append({"title": title, "reason": "duplicate_pending_queue"})
            continue

        if _is_action_recent_duplicate(state, action, title=title):
            event["skipped"].append({"title": title, "reason": "recent_duplicate"})
            continue

        if executed_this_tick >= tick_budget:
            queued = _proposal_to_queue_item(clean, "tick_exec_budget_limit")
            enqueue_result = _enqueue(queued)
            if enqueue_result.get("added"):
                pending_fingerprints.add(_ensure_item_fingerprint(queued))
                pending_semantic_keys.add(_ensure_item_semantic_key(queued))
                event["queued"].append(
                    {"id": queued["id"], "title": queued.get("title", ""), "blocked": queued.get("reason_blocked", "")}
                )
            else:
                event["skipped"].append({"title": title, "reason": str(enqueue_result.get("reason", "duplicate_pending_queue"))})
            continue

        if not action:
            queued = _proposal_to_queue_item(proposal, "invalid_action_payload")
            enqueue_result = _enqueue(queued)
            if enqueue_result.get("added"):
                pending_fingerprints.add(_ensure_item_fingerprint(queued))
                pending_semantic_keys.add(_ensure_item_semantic_key(queued))
                event["queued"].append({"id": queued["id"], "title": queued.get("title", ""), "blocked": queued.get("reason_blocked", "")})
            else:
                event["skipped"].append({"title": title, "reason": str(enqueue_result.get("reason", "duplicate_pending_queue"))})
            continue

        if confidence < confidence_threshold:
            queued = _proposal_to_queue_item(clean, "confidence_below_threshold")
            enqueue_result = _enqueue(queued)
            if enqueue_result.get("added"):
                pending_fingerprints.add(_ensure_item_fingerprint(queued))
                pending_semantic_keys.add(_ensure_item_semantic_key(queued))
                event["queued"].append({"id": queued["id"], "title": queued.get("title", ""), "blocked": queued.get("reason_blocked", "")})
            else:
                event["skipped"].append({"title": title, "reason": str(enqueue_result.get("reason", "duplicate_pending_queue"))})
            continue

        if risk != "low":
            queued = _proposal_to_queue_item(clean, "risk_not_low")
            enqueue_result = _enqueue(queued)
            if enqueue_result.get("added"):
                pending_fingerprints.add(_ensure_item_fingerprint(queued))
                pending_semantic_keys.add(_ensure_item_semantic_key(queued))
                event["queued"].append({"id": queued["id"], "title": queued.get("title", ""), "blocked": queued.get("reason_blocked", "")})
            else:
                event["skipped"].append({"title": title, "reason": str(enqueue_result.get("reason", "duplicate_pending_queue"))})
            continue

        if action_type == "web_search":
            if web_count >= SETTINGS.autonomy_max_web_results_per_tick:
                queued = _proposal_to_queue_item(clean, "web_search_tick_limit")
                enqueue_result = _enqueue(queued)
                if enqueue_result.get("added"):
                    pending_fingerprints.add(_ensure_item_fingerprint(queued))
                    pending_semantic_keys.add(_ensure_item_semantic_key(queued))
                    event["queued"].append({"id": queued["id"], "title": queued.get("title", ""), "blocked": queued.get("reason_blocked", "")})
                else:
                    event["skipped"].append({"title": title, "reason": str(enqueue_result.get("reason", "duplicate_pending_queue"))})
                continue

        if _safe_int(state.get("autoexec_count"), 0) >= autoexec_limit:
            queued = _proposal_to_queue_item(clean, "hourly_autoexec_limit")
            enqueue_result = _enqueue(queued)
            if enqueue_result.get("added"):
                pending_fingerprints.add(_ensure_item_fingerprint(queued))
                pending_semantic_keys.add(_ensure_item_semantic_key(queued))
                event["queued"].append({"id": queued["id"], "title": queued.get("title", ""), "blocked": queued.get("reason_blocked", "")})
            else:
                event["skipped"].append({"title": title, "reason": str(enqueue_result.get("reason", "duplicate_pending_queue"))})
            continue

        result = _execute_low_risk_action(action)
        if result.get("ok"):
            state["autoexec_count"] = _safe_int(state.get("autoexec_count"), 0) + 1
            if action_type == "web_search":
                web_count += 1
            executed_this_tick += 1
            _remember_action(state, action, title=title, source="autoexec")
            event["executed"].append(
                {
                    "title": title,
                    "action_type": action_type,
                    "result": str(result.get("result", "")),
                }
            )
        else:
            queued = _proposal_to_queue_item(clean, f"execution_failed: {result.get('result')}")
            enqueue_result = _enqueue(queued)
            if enqueue_result.get("added"):
                pending_fingerprints.add(_ensure_item_fingerprint(queued))
                pending_semantic_keys.add(_ensure_item_semantic_key(queued))
                event["queued"].append({"id": queued["id"], "title": queued.get("title", ""), "blocked": queued.get("reason_blocked", "")})
            else:
                event["skipped"].append({"title": title, "reason": str(enqueue_result.get("reason", "duplicate_pending_queue"))})

    _append_jsonl(DECISIONS_PATH, event)
    _save_state(state)
    lines = [
        f"## {datetime.now().strftime('%H:%M:%S')} | Tick",
        f"- thought: {event.get('thought', '')}",
        f"- proposals_count: {len(event.get('proposals', []))}",
        f"- tick_budget: {tick_budget}",
    ]
    for p in event.get("proposals", []):
        lines.append(
            f"  - proposal: {p.get('title','')} | risk={p.get('risk','')} | "
            f"conf={p.get('confidence',0)} | action={p.get('action_type','')}"
        )
    if event.get("executed"):
        lines.append(f"- executed_count: {len(event.get('executed', []))}")
        for e in event.get("executed", []):
            lines.append(
                f"  - executed: {e.get('title','')} | action={e.get('action_type','')} | "
                f"result={_sanitize_text(e.get('result',''), 200)}"
            )
    if event.get("queued"):
        lines.append(f"- queued_count: {len(event.get('queued', []))}")
        for q in event.get("queued", []):
            lines.append(
                f"  - queued: {q.get('id','')} | title={q.get('title','')} | "
                f"blocked={q.get('blocked','')}"
            )
    if event.get("skipped"):
        lines.append(f"- skipped_count: {len(event.get('skipped', []))}")
        for s in event.get("skipped", []):
            lines.append(
                f"  - skipped: {s.get('title','')} | reason={s.get('reason','')}"
            )
    if event.get("errors"):
        lines.append(f"- errors: {', '.join(event.get('errors', []))}")
    _append_daily_log_lines(lines)
    return event


def get_autonomy_state():
    state = _load_state()
    recent_actions = _prune_recent_actions(state)
    queue = _load_queue()
    queue, changed = _dedupe_queue_items(queue)
    if changed:
        _save_queue(queue)
        _save_state(state)
    return {
        "enabled": bool(SETTINGS.autonomy_enabled),
        "interval_seconds": int(SETTINGS.autonomy_interval_seconds),
        "autoexec_count_this_hour": _safe_int(state.get("autoexec_count"), 0),
        "ticks_count": _safe_int(state.get("ticks_count"), 0),
        "last_tick_at": str(state.get("last_tick_at", "")),
        "queue_size": len(queue),
        "recent_actions_count": len(recent_actions),
        "state_dir": str(SETTINGS.autonomy_state_dir),
        "decisions_log_path": str(DECISIONS_PATH),
        "daily_log_path": str(_daily_log_path()),
        "notes_dir": str(SETTINGS.allowed_root / "autonomy_notes"),
    }


def get_autonomy_queue(limit=50):
    items = _load_queue()
    items, changed = _dedupe_queue_items(items)
    if changed:
        _save_queue(items)
    return items[-int(limit) :] if items else []


def approve_queue_item(item_id: str, reviewer: str = "manual"):
    queued = _pop_queue_item(item_id)
    if not queued:
        return {"ok": False, "error": "queue_item_not_found", "id": str(item_id)}

    action = queued.get("action", {}) if isinstance(queued.get("action", {}), dict) else {}
    action = _sanitize_action(action)
    if not action:
        event = {
            "timestamp": _now_iso(),
            "kind": "queue_decision",
            "decision": "APPROVED_INVALID_ACTION",
            "reviewer": str(reviewer),
            "id": str(item_id),
            "result": "invalid_action_payload",
        }
        _append_jsonl(DECISIONS_PATH, event)
        return {"ok": False, "error": "invalid_action_payload", "id": str(item_id)}

    result = _execute_low_risk_action(action)
    if result.get("ok"):
        state = _load_state()
        _remember_action(
            state,
            action,
            title=str(queued.get("title", "")),
            source="manual_approve",
        )
        _save_state(state)
    event = {
        "timestamp": _now_iso(),
        "kind": "queue_decision",
        "decision": "APPROVED",
        "reviewer": str(reviewer),
        "id": str(item_id),
        "action_type": str(action.get("type", "")),
        "result": str(result.get("result", "")),
        "ok": bool(result.get("ok")),
    }
    _append_jsonl(DECISIONS_PATH, event)
    _append_daily_log_lines(
        [
            f"## {datetime.now().strftime('%H:%M:%S')} | Queue APPROVED",
            f"- id: {item_id}",
            f"- reviewer: {reviewer}",
            f"- action_type: {event.get('action_type','')}",
            f"- ok: {event.get('ok')}",
            f"- result: {_sanitize_text(event.get('result',''), 220)}",
        ]
    )
    return {"ok": bool(result.get("ok")), "id": str(item_id), "result": str(result.get("result", ""))}


def reject_queue_item(item_id: str, reviewer: str = "manual", reason: str = ""):
    queued = _pop_queue_item(item_id)
    if not queued:
        return {"ok": False, "error": "queue_item_not_found", "id": str(item_id)}

    event = {
        "timestamp": _now_iso(),
        "kind": "queue_decision",
        "decision": "REJECTED",
        "reviewer": str(reviewer),
        "id": str(item_id),
        "reason": _sanitize_text(reason, 500),
    }
    _append_jsonl(DECISIONS_PATH, event)
    _append_daily_log_lines(
        [
            f"## {datetime.now().strftime('%H:%M:%S')} | Queue REJECTED",
            f"- id: {item_id}",
            f"- reviewer: {reviewer}",
            f"- reason: {_sanitize_text(reason, 220)}",
        ]
    )
    return {"ok": True, "id": str(item_id), "result": "rejected"}


def decide_queue_item(item_id: str, decision: str, reviewer: str = "manual", reason: str = ""):
    normalized = str(decision or "").strip().lower()
    if normalized == "approve":
        return approve_queue_item(item_id=item_id, reviewer=reviewer)
    if normalized == "reject":
        return reject_queue_item(item_id=item_id, reviewer=reviewer, reason=reason)
    return {"ok": False, "error": "invalid_decision", "allowed": ["approve", "reject"]}


def run_autonomy_loop(stop_event: threading.Event | None = None):
    if not SETTINGS.autonomy_enabled:
        print("[*] Autonomy loop disabled (PIORUN_AUTONOMY_ENABLED=false).")
        return

    interval = max(30, int(SETTINGS.autonomy_interval_seconds))
    print(f"[*] Autonomy loop active ({interval}s).")
    while True:
        try:
            event = autonomy_tick()
            print(
                f"[*] Autonomy tick: executed={len(event.get('executed', []))}, "
                f"queued={len(event.get('queued', []))}, errors={len(event.get('errors', []))}"
            )
        except Exception as e:
            _append_jsonl(
                DECISIONS_PATH,
                {"timestamp": _now_iso(), "kind": "tick_error", "error": str(e)},
            )
            print(f"[!] Autonomy tick error: {e}")

        if stop_event is not None:
            if stop_event.wait(timeout=interval):
                break
        else:
            time.sleep(interval)
