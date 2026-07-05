import subprocess
import os
import tempfile
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()
SANDBOX_DIR = str(SETTINGS.sandbox_dir)

def execute_python(code):
    """Uruchamia kod Python w sandboksie i zwraca wynik."""
    if not os.path.exists(SANDBOX_DIR):
        os.makedirs(SANDBOX_DIR)
    
    with tempfile.NamedTemporaryFile(suffix=".py", dir=SANDBOX_DIR, delete=False, mode='w', encoding='utf-8') as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(["python", temp_path], capture_output=True, text=True, timeout=30)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        # Można zostawić do debugowania lub usuwać:
        # os.remove(temp_path)
        pass

def execute_node(code):
    """Uruchamia kod Node.js w sandboksie i zwraca wynik."""
    if not os.path.exists(SANDBOX_DIR):
        os.makedirs(SANDBOX_DIR)
    
    with tempfile.NamedTemporaryFile(suffix=".js", dir=SANDBOX_DIR, delete=False, mode='w', encoding='utf-8') as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(["node", temp_path], capture_output=True, text=True, timeout=30)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        # os.remove(temp_path)
        pass


def run_code(code, language="python"):
    """Kompatybilny wrapper dla starszego API narzędzia test_code."""
    lang = (language or "python").lower()
    if lang in ("python", "py"):
        return str(execute_python(code))
    if lang in ("node", "javascript", "js"):
        return str(execute_node(code))
    return "Nieobslugiwany jezyk. Dostepne: python, node."

if __name__ == "__main__":
    # Test
    print(execute_python("print('Hello from Python Sandbox!')"))
