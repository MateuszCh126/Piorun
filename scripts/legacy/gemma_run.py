import subprocess
import os
import sys
from core.config import get_settings

def run_model(model_name="9b"):
    settings = get_settings()
    base_path = str(settings.workspace_root)
    models = {
        "9b": os.path.join(base_path, "models", "gemma-4-9b-q4.gguf"),
        "31b": os.path.join(base_path, "models", "gemma-4-31b-q4.gguf")
    }
    
    llama_path = os.path.join(base_path, "llama_cpp", "llama-cli.exe")
    
    if not os.path.exists(models[model_name]):
        print(f"Błąd: Model {model_name} nie został jeszcze w pełni pobrany.")
        return

    print(f"--- Uruchamiam Gemma-4 {model_name.upper()} ---")
    print("Wykorzystuję GPU (RTX 5050)...")
    
    cmd = [
        llama_path,
        "-m", models[model_name],
        "-ngl", "99", # Zawsze prbuj wrzuci wszystko na GPU
        "-cnv", # Tryb konwersacji (nowoczesne -i)
        "--color", "on"
    ]
    
    try:
        subprocess.run(cmd)
    except Exception as e:
        print(f"Wystąpił błąd podczas uruchamiania: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_model(sys.argv[1].lower())
    else:
        print("Użycie: python gemma_run.py [9b|31b]")
        run_model("9b")
