import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _parse_env_file(env_path: Path):
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    runtime_root: Path
    workspace_root: Path
    history_db: Path
    tasks_db: Path
    token_path: Path
    workdir: Path
    sessions_root: Path
    notes_root: Path
    autonomy_log: Path
    whisper_model_path: Path
    memory_vector_db: Path
    sandbox_dir: Path
    backup_dir: Path
    agent_credentials_path: Path
    gcal_credentials_path: Path
    attachments_dir: Path
    llama_base_url: str
    llm_health_timeout_seconds: int
    ops_api_host: str
    ops_api_port: int
    model_name: str
    allowed_root: Path
    context_max_tokens: int
    context_keep_recent_tokens: int
    summary_refresh_every_messages: int
    summary_recent_limit: int
    autonomy_enabled: bool
    autonomy_interval_seconds: int
    autonomy_min_confidence: int
    autonomy_max_autoexec_per_hour: int
    autonomy_max_web_results_per_tick: int
    autonomy_max_autoexec_per_tick: int
    autonomy_action_cooldown_minutes: int
    autonomy_heartbeat_cooldown_minutes: int
    autonomy_planner_timeout_seconds: int
    autonomy_planner_max_tokens: int
    autonomy_state_dir: Path
    memory_recall_enabled: bool
    memory_embedding_model: str
    memory_recall_top_k: int
    memory_recall_max_distance: float
    autonomy_failed_ttl_days: int
    autonomy_reminders_enabled: bool
    autonomy_reminder_hours: int
    autonomy_reminder_cooldown_minutes: int
    log_retention_days: int


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser()


def _int_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return int(default)
    try:
        return int(raw)
    except ValueError:
        return int(default)


def _float_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _bootstrap_env():
    explicit_env_file = os.environ.get("PIORUN_ENV_FILE")
    if explicit_env_file:
        _parse_env_file(Path(explicit_env_file).expanduser())
    _parse_env_file(PROJECT_ROOT / ".env")


def _default_user_home() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home())))


def _build_settings() -> Settings:
    _bootstrap_env()

    user_home = _default_user_home()
    desktop_root = _path_from_env("PIORUN_DESKTOP_ROOT", user_home / "Desktop")

    runtime_root = _path_from_env("PIORUN_RUNTIME_ROOT", user_home / ".piorun")
    workdir = _path_from_env("PIORUN_WORKDIR", desktop_root / "Piorun")
    sessions_root = _path_from_env("PIORUN_SESSIONS_ROOT", workdir / "sessions")
    notes_root = _path_from_env("PIORUN_NOTES_ROOT", workdir / "notes")

    workspace_root = _path_from_env("PIORUN_WORKSPACE_ROOT", PROJECT_ROOT)
    history_db = _path_from_env("PIORUN_HISTORY_DB", runtime_root / "history.db")
    tasks_db = _path_from_env("PIORUN_TASKS_DB", runtime_root / "tasks.db")
    token_path = _path_from_env("PIORUN_GCAL_TOKEN_PATH", runtime_root / "token.json")
    autonomy_log = _path_from_env("PIORUN_AUTONOMY_LOG", workdir / "autonomous_log.md")
    whisper_model_path = _path_from_env("PIORUN_WHISPER_MODEL_PATH", workdir / "whisper-large-v3")
    memory_vector_db = _path_from_env("PIORUN_MEMORY_VECTOR_DB", workspace_root / ".memory_db")
    sandbox_dir = _path_from_env("PIORUN_SANDBOX_DIR", workspace_root / ".sandbox")
    backup_dir = _path_from_env("PIORUN_BACKUP_DIR", runtime_root / "backups")
    agent_credentials_path = _path_from_env("PIORUN_AGENT_CREDENTIALS_PATH", workspace_root / "agent_credentials.json")
    gcal_credentials_path = _path_from_env("PIORUN_GCAL_CREDENTIALS_PATH", workspace_root / "credentials.json")
    attachments_dir = _path_from_env("PIORUN_ATTACHMENTS_DIR", workdir)
    allowed_root = _path_from_env("PIORUN_ALLOWED_ROOT", workdir)

    llama_base_url = os.environ.get("PIORUN_LLM_BASE_URL", "http://localhost:8080/v1")
    llm_health_timeout_seconds = _int_from_env("PIORUN_LLM_HEALTH_TIMEOUT_SECONDS", 3)
    ops_api_host = os.environ.get("PIORUN_OPS_API_HOST", "127.0.0.1")
    ops_api_port = _int_from_env("PIORUN_OPS_API_PORT", 8787)
    model_name = os.environ.get("PIORUN_MODEL_NAME", "gemma-4-9b")
    context_max_tokens = _int_from_env("PIORUN_CONTEXT_MAX_TOKENS", 12000)
    context_keep_recent_tokens = _int_from_env("PIORUN_CONTEXT_KEEP_RECENT_TOKENS", 5000)
    summary_refresh_every_messages = _int_from_env("PIORUN_SUMMARY_REFRESH_EVERY_MESSAGES", 8)
    summary_recent_limit = _int_from_env("PIORUN_SUMMARY_RECENT_LIMIT", 40)
    autonomy_enabled = _bool_from_env("PIORUN_AUTONOMY_ENABLED", False)
    autonomy_interval_seconds = _int_from_env("PIORUN_AUTONOMY_INTERVAL_SECONDS", 300)
    autonomy_min_confidence = _int_from_env("PIORUN_AUTONOMY_MIN_CONFIDENCE_PERCENT", 75)
    autonomy_max_autoexec_per_hour = _int_from_env("PIORUN_AUTONOMY_MAX_AUTOEXEC_PER_HOUR", 4)
    autonomy_max_web_results_per_tick = _int_from_env("PIORUN_AUTONOMY_MAX_WEB_RESULTS_PER_TICK", 2)
    autonomy_max_autoexec_per_tick = _int_from_env("PIORUN_AUTONOMY_MAX_AUTOEXEC_PER_TICK", 2)
    autonomy_action_cooldown_minutes = _int_from_env("PIORUN_AUTONOMY_ACTION_COOLDOWN_MINUTES", 180)
    autonomy_heartbeat_cooldown_minutes = _int_from_env("PIORUN_AUTONOMY_HEARTBEAT_COOLDOWN_MINUTES", 720)
    autonomy_planner_timeout_seconds = _int_from_env("PIORUN_AUTONOMY_PLANNER_TIMEOUT_SECONDS", 60)
    autonomy_planner_max_tokens = _int_from_env("PIORUN_AUTONOMY_PLANNER_MAX_TOKENS", 1200)
    autonomy_state_dir = _path_from_env("PIORUN_AUTONOMY_STATE_DIR", runtime_root / "autonomy")
    memory_recall_enabled = _bool_from_env("PIORUN_MEMORY_RECALL_ENABLED", True)
    memory_embedding_model = os.environ.get(
        "PIORUN_MEMORY_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    memory_recall_top_k = _int_from_env("PIORUN_MEMORY_RECALL_TOP_K", 5)
    memory_recall_max_distance = _float_from_env("PIORUN_MEMORY_RECALL_MAX_DISTANCE", 0.65)
    autonomy_failed_ttl_days = _int_from_env("PIORUN_AUTONOMY_FAILED_TTL_DAYS", 7)
    autonomy_reminders_enabled = _bool_from_env("PIORUN_AUTONOMY_REMINDERS_ENABLED", True)
    autonomy_reminder_hours = _int_from_env("PIORUN_AUTONOMY_REMINDER_HOURS", 48)
    autonomy_reminder_cooldown_minutes = _int_from_env("PIORUN_AUTONOMY_REMINDER_COOLDOWN_MINUTES", 1200)
    log_retention_days = _int_from_env("PIORUN_LOG_RETENTION_DAYS", 90)

    return Settings(
        project_root=PROJECT_ROOT,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
        history_db=history_db,
        tasks_db=tasks_db,
        token_path=token_path,
        workdir=workdir,
        sessions_root=sessions_root,
        notes_root=notes_root,
        autonomy_log=autonomy_log,
        whisper_model_path=whisper_model_path,
        memory_vector_db=memory_vector_db,
        sandbox_dir=sandbox_dir,
        backup_dir=backup_dir,
        agent_credentials_path=agent_credentials_path,
        gcal_credentials_path=gcal_credentials_path,
        attachments_dir=attachments_dir,
        llama_base_url=llama_base_url,
        llm_health_timeout_seconds=llm_health_timeout_seconds,
        ops_api_host=ops_api_host,
        ops_api_port=ops_api_port,
        model_name=model_name,
        allowed_root=allowed_root,
        context_max_tokens=context_max_tokens,
        context_keep_recent_tokens=context_keep_recent_tokens,
        summary_refresh_every_messages=summary_refresh_every_messages,
        summary_recent_limit=summary_recent_limit,
        autonomy_enabled=autonomy_enabled,
        autonomy_interval_seconds=autonomy_interval_seconds,
        autonomy_min_confidence=autonomy_min_confidence,
        autonomy_max_autoexec_per_hour=autonomy_max_autoexec_per_hour,
        autonomy_max_web_results_per_tick=autonomy_max_web_results_per_tick,
        autonomy_max_autoexec_per_tick=autonomy_max_autoexec_per_tick,
        autonomy_action_cooldown_minutes=autonomy_action_cooldown_minutes,
        autonomy_heartbeat_cooldown_minutes=autonomy_heartbeat_cooldown_minutes,
        autonomy_planner_timeout_seconds=autonomy_planner_timeout_seconds,
        autonomy_planner_max_tokens=autonomy_planner_max_tokens,
        autonomy_state_dir=autonomy_state_dir,
        memory_recall_enabled=memory_recall_enabled,
        memory_embedding_model=memory_embedding_model,
        memory_recall_top_k=memory_recall_top_k,
        memory_recall_max_distance=memory_recall_max_distance,
        autonomy_failed_ttl_days=autonomy_failed_ttl_days,
        autonomy_reminders_enabled=autonomy_reminders_enabled,
        autonomy_reminder_hours=autonomy_reminder_hours,
        autonomy_reminder_cooldown_minutes=autonomy_reminder_cooldown_minutes,
        log_retention_days=log_retention_days,
    )


def ensure_runtime_dirs(settings: Settings):
    required_dirs = [
        settings.runtime_root,
        settings.workdir,
        settings.sessions_root,
        settings.notes_root,
        settings.memory_vector_db,
        settings.sandbox_dir,
        settings.backup_dir,
        settings.autonomy_state_dir,
        settings.attachments_dir,
    ]
    for directory in required_dirs:
        directory.mkdir(parents=True, exist_ok=True)

    # Upewniamy się, że katalogi dla plików istnieją.
    for file_path in [settings.history_db, settings.tasks_db, settings.token_path, settings.autonomy_log]:
        file_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = _build_settings()
    ensure_runtime_dirs(settings)
    return settings
