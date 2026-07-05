import os
import json
import sqlite3
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
import core.db_schema as db_schema
from core.config import get_settings

SETTINGS = get_settings()
DB_PATH = str(SETTINGS.tasks_db)
SQLITE_URL = f"sqlite:///{DB_PATH}"

# Konfiguracja JobStore (SQLite)
jobstores = {
    'default': SQLAlchemyJobStore(
        url=SQLITE_URL,
        engine_options={
            "connect_args": {"timeout": 30}
        }
    )
}

scheduler = BackgroundScheduler(jobstores=jobstores)

def get_db_connection():
    """Tworzy bezpieczne polaczenie z baza zadan (mode=WAL)."""
    db_schema.ensure_tasks_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def log_audit(event_type, description):
    """Zapisuje ślad audytowy do bazy danych."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)", (event_type, description))
            conn.commit()
    except Exception as e:
        print(f"[!] Blad audytu: {e}")

def task_wrapper(task_id, func, *args, **kwargs):
    """Wrapper z logiką atomowych transakcji i audytem."""
    # 1. Pobranie danych zadania (krótkie połączenie)
    row = None
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT retries_remaining, name FROM tasks WHERE job_id = ?", (task_id,))
            row = cursor.fetchone()
    except Exception as e:
        log_audit("ERROR", f"Blad pobierania zadania {task_id}: {e}")
        return

    if not row:
        log_audit("ERROR", f"Proba wykonania nieznanego zadania: {task_id}")
        return

    retries, name = row
    log_audit("START", f"Uruchamiam zadanie: {name} (ID: {task_id})")

    try:
        # 2. Wykonanie zadania (BEZ otwartej bazy - tu może schodzić czas)
        result = func(*args, **kwargs)
        
        # 3. Aktualizacja na SUCCESS (krótkie połączenie)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET status = 'SUCCESS', actual_time = ? WHERE job_id = ?", 
                           (datetime.now().isoformat(), task_id))
            conn.commit()
        log_audit("SUCCESS", f"Zadanie {name} ukonczone: {str(result)[:100]}")
        
    except Exception as e:
        error_msg = str(e)
        new_retries = retries - 1
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if new_retries > 0:
                cursor.execute("UPDATE tasks SET status = 'RETRY', retries_remaining = ?, last_error = ? WHERE job_id = ?",
                               (new_retries, error_msg, task_id))
                log_audit("RETRY", f"Zadanie {name} nieudane. Pozostalo prob: {new_retries}. Blad: {error_msg}")
            else:
                cursor.execute("UPDATE tasks SET status = 'FATAL', retries_remaining = 0, last_error = ? WHERE job_id = ?",
                               (error_msg, task_id))
                log_audit("FATAL", f"Zadanie {name} przekroczylo limit prob. Blad krytyczny: {error_msg}")
            conn.commit()
        raise e

def listener(event):
    if event.code == EVENT_JOB_MISSED:
        log_audit("MISSED", f"Zadanie przegapione! Silnik spróbuje je nadgonić (Misfire).")

scheduler.add_listener(listener, EVENT_JOB_MISSED)

def start_engine():
    if not scheduler.running:
        db_schema.ensure_tasks_db(DB_PATH)
        scheduler.start()
        log_audit("SYSTEM", "Piorun Task Engine wystartował.")

def add_persistent_task(name, run_date, func, args_list, task_type="GENERIC"):
    """Dodaje jednorazowe zadanie do bazy i harmonogramu."""
    job = scheduler.add_job(
        task_wrapper, 
        'date', 
        run_date=run_date, 
        args=[None, func] + args_list,
        misfire_grace_time=3600
    )
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (name, job_id, type, schedule_time, payload) VALUES (?, ?, ?, ?, ?)",
                       (name, job.id, task_type, run_date.isoformat(), json.dumps(args_list)))
        conn.commit()
    
    scheduler.modify_job(job.id, args=[job.id, func] + args_list)
    return job.id

def add_recurring_task(name, cron_expr, func, args_list, task_type="RECURRING"):
    """Dodaje zadanie cykliczne (np. codzienne) do bazy i procesora."""
    # cron_expr format: "0 7 * * *" (min hour day month day_of_week)
    from apscheduler.triggers.cron import CronTrigger
    trigger = CronTrigger.from_crontab(cron_expr)
    
    job = scheduler.add_job(
        task_wrapper,
        trigger,
        args=[None, func] + args_list,
        id=f"rec_{name.lower().replace(' ', '_')}",
        replace_existing=True
    )
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Sprawdzamy czy juz jest w bazie
        cursor.execute("SELECT id FROM tasks WHERE job_id = ?", (job.id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO tasks (name, job_id, type, schedule_time, payload) VALUES (?, ?, ?, ?, ?)",
                           (name, job.id, task_type, cron_expr, json.dumps(args_list)))
        conn.commit()
    
    scheduler.modify_job(job.id, args=[job.id, func] + args_list)
    return job.id

def sync_pending_tasks():
    """Synchronizuje zadania PENDING z bazy do aktywnego harmonogramu."""
    pending_tasks = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Szukamy zadań PENDING, które nie są jeszcze w APScheduler
            cursor.execute("SELECT id, name, job_id, schedule_time, payload, type FROM tasks WHERE status = 'PENDING'")
            pending_tasks = cursor.fetchall()
    except Exception as e:
        print(f"[!] Blad odczytu zadań PENDING: {e}")
        return
    
    existing_jobs = [job.id for job in scheduler.get_jobs()]
    import tools.mailer as mailer # Import tutaj, aby uniknąć cyklicznych zależności
    
    for task in pending_tasks:
        t_id, t_name, t_job_id, t_time, t_payload, t_type = task
        if t_job_id not in existing_jobs:
            print(f"[*] Synchronizacja: Dodaję brakujące zadanie '{t_name}' do silnika...")
            try:
                payload = json.loads(t_payload) if t_payload else []
                if not isinstance(payload, list):
                    payload = [payload]
                # Na razie zakładamy, że to EMAIL, bo tylko to mamy zaplanowane
                func = mailer.send_email

                if str(t_type).upper() == "RECURRING":
                    from apscheduler.triggers.cron import CronTrigger
                    trigger = CronTrigger.from_crontab(t_time)
                    scheduler.add_job(
                        task_wrapper,
                        trigger,
                        args=[t_job_id, func] + payload,
                        id=t_job_id,
                        replace_existing=True,
                        misfire_grace_time=3600
                    )
                else:
                    run_date = datetime.fromisoformat(t_time)
                    scheduler.add_job(
                        task_wrapper,
                        'date',
                        run_date=run_date,
                        args=[t_job_id, func] + payload,
                        id=t_job_id,  # Używamy tego samego ID
                        misfire_grace_time=3600
                    )
            except Exception as e:
                print(f"[!] Błąd synchronizacji zadania {t_id}: {e}")
