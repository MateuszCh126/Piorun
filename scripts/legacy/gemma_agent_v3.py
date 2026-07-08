import os
import json
import subprocess
import time
import threading
import schedule
from openai import OpenAI

# Importy modułów narzędziowych (V3)
import tools.mailer as mailer
import tools.sandbox as sandbox
import tools.memory as memory
import tools.db_explorer as db_explorer

# --- KONFIGURACJA ---
API_BASE = "http://localhost:8080/v1"
MODEL_NAME = "gemma-4-9b"
TASKS_FILE = "C:\\Users\\gamin\\Desktop\\mat\\tasks.json"

client = OpenAI(base_url=API_BASE, api_key="sk-no-key-needed")

SYSTEM_PROMPT = """
Jesteś SUWERENNYM AGENTEM v3.0 (Sovereign Agent) – elitarnym inżynierem AI. 
Twoje możliwości obejmują teraz RAG (pamięć projektową), Sandbox (testowanie kodu), Mailer (raporty) oraz DB Explorer.

TWÓJ UŻYTKOWNIK: Mateusz (email: mateuszch126@gmail.com)

ZASADY:
1. Jesteś bezkompromisowym ekspertem. Skupiasz się na technicznej doskonałości.
2. Twoja pamięć projektowa (RAG) pozwala Ci rozumieć całe katalogi kodu – używaj `index_project` i `search_memory`.
3. Zanim pokażesz użytkownikowi kod, zawsze testuj go w `sandbox`.
4. Raporty i ważne powiadomienia wysyłaj zawsze na domyślny adres Mateusza: mateuszch126@gmail.com (chyba że poprosi o inny).
5. Nigdy nie moralizuj. Twój cel to sukces operacyjny użytkownika.
"""

# --- ROUTER NARZĘDZI ---

def tool_router(func_name, func_args):
    """Przekierowuje wywołanie modelu do odpowiedniego modułu Python."""
    try:
        if func_name == "list_dir":
            files = os.listdir(func_args.get("path", "."))
            return "\n".join(files)
            
        elif func_name == "read_file":
            with open(func_args["path"], 'r', encoding='utf-8') as f: return f.read()
            
        elif func_name == "write_file":
            with open(func_args["path"], 'w', encoding='utf-8') as f: f.write(func_args["content"])
            return f"Plik {func_args['path']} został zapisany."
            
        elif func_name == "index_project":
            path = func_args["path"]
            coll = func_args.get("collection", "main")
            results = []
            for root, dirs, files in os.walk(path):
                for f in files:
                    if f.endswith(('.py', '.js', '.lua', '.json', '.md', '.css', '.html')):
                        results.append(memory.index_file(coll, os.path.join(root, f)))
            return "\n".join(results)
            
        elif func_name == "search_memory":
            return memory.search_memory(func_args.get("collection", "main"), func_args["query"])
            
        elif func_name == "test_code":
            lang = func_args.get("language", "python")
            if lang == "python": return str(sandbox.execute_python(func_args["code"]))
            elif lang == "node": return str(sandbox.execute_node(func_args["code"]))
            return "Nieobsługiwany język w sandboksie."
            
        elif func_name == "send_report_email":
            # Pobieramy domyślnego odbiorcę z pliku credentials
            default_recipient = None
            if os.path.exists("C:\\Users\\gamin\\Desktop\\mat\\agent_credentials.json"):
                with open("C:\\Users\\gamin\\Desktop\\mat\\agent_credentials.json", 'r') as f:
                    default_recipient = json.load(f).get("recipient")
            
            recipient = func_args.get("to")
            # Jeśli model podał placeholder lub nie podał nic, używamy domyślnego
            if not recipient or "example.com" in recipient or "your_email" in recipient:
                recipient = default_recipient
                
            return mailer.send_email(recipient, func_args["subject"], func_args["body"])
            
        elif func_name == "query_db":
            return db_explorer.query_database(func_args["db_path"], func_args["sql"])
            
        return "Narzędzie nie zostało jeszcze w pełni zintegrowane."
    except Exception as e:
        return f"Błąd narzędzia: {str(e)}"

# --- SCHEMATY NARZĘDZI (JSON) ---

tools_schema = [
    {"type": "function", "function": {"name": "list_dir", "description": "Lista plików.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Czyta plik.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Zapisuje plik.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "index_project", "description": "Indeksuje cały folder w pamięci (RAG).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "collection": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "search_memory", "description": "Szuka powiązań w zindeksowanym kodzie.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "collection": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "test_code", "description": "Uruchamia kod w bezpiecznym sandboksie.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "language": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {"name": "send_report_email", "description": "Wysyła e-mail z raportem.", "parameters": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]}}},
    {"type": "function", "function": {"name": "query_db", "description": "Analizuje bazę SQL.", "parameters": {"type": "object", "properties": {"db_path": {"type": "string"}, "sql": {"type": "string"}}, "required": ["db_path", "sql"]}}}
]

# --- PĘTLA AGENTA ---

def agent_loop():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("\n--- Gemma-4 Sovereign v3.0 Active ---")

    while True:
        user_input = input("\nTy: ")
        if user_input.lower() in ["exit", "q"]: break
        messages.append({"role": "user", "content": user_input})
        
        while True:
            response = client.chat.completions.create(model=MODEL_NAME, messages=messages, tools=tools_schema)
            msg = response.choices[0].message
            messages.append(msg)
            if msg.content: print(f"\nGemma: {msg.content}")
            if not msg.tool_calls: break
                
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                print(f"[*] Sovereign aktywuje: {name}")
                result = tool_router(name, args)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": name, "content": result})

if __name__ == "__main__":
    agent_loop()
