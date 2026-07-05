import sys
import os
# Dodajemy folder główny do path, aby móc importować moduły
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import core.scheduler_engine as ste
import tools.autonomous_engine as auto

def setup():
    print("[*] Rejestracja Autonomicznego Trybu Porannego (07:00)...")
    
    # Cron: 0 7 * * * (0 min, 7 godz, każdy dzień)
    cron_expr = "0 7 * * *"
    
    try:
        ste.start_engine()
        job_id = ste.add_recurring_task(
            name="Morning Autonomy",
            cron_expr=cron_expr,
            func=auto.run_morning_routine,
            args_list=[]
        )
        print(f"[OK] Zadanie zarejestrowane! ID: {job_id}")
        print("[*] Piorun będzie się budził codziennie o 07:00.")
    except Exception as e:
        print(f"[!] Błąd rejestracji: {e}")

if __name__ == "__main__":
    setup()
