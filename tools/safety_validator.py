import os
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()
ALLOWED_ROOT = str(SETTINGS.allowed_root)

def is_action_safe(action_name, params):
    r"""
    Weryfikuje czy akcja podjęta w trybie autonomicznym jest bezpieczna.
    Zasada: Autonomia może działać tylko wewnątrz folderu Desktop\Piorun.
    """
    
    # 1. Zakazane narzędzia w trybie pełnej autonomii
    BANNED_TOOLS = ["test_code", "schedule_task"]
    if action_name in BANNED_TOOLS:
        return False, f"Narzędzie {action_name} jest zablokowane w trybie autonomicznym."

    # 2. Weryfikacja zapisu plików
    if action_name == "write_file":
        path = params.get("path", "")
        normalized_path = os.path.abspath(os.path.normpath(path))
        allowed_root = os.path.abspath(os.path.normpath(ALLOWED_ROOT))
        try:
            in_allowed_tree = os.path.commonpath([allowed_root, normalized_path]) == allowed_root
        except ValueError:
            in_allowed_tree = False
        if not in_allowed_tree:
            return False, f"Próba zapisu poza obszarem dozwolonym: {path}"

    # 3. Weryfikacja maili
    if action_name == "send_report_email":
        to_email = params.get("to", "").lower()
        if to_email != "mateuszch126@gmail.com":
            return False, "Autonomia może wysyłać maile tylko do Mateusza."

    return True, "OK"
