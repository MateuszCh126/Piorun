import imaplib
import email
import json
import os
import time
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()
CREDENTIALS_PATH = str(SETTINGS.agent_credentials_path)
ATTACHMENTS_DIR = str(SETTINGS.attachments_dir)

def get_creds():
    with open(CREDENTIALS_PATH, 'r') as f:
        return json.load(f)

def fetch_unread_emails():
    """Pobiera nieprzeczytane maile od zdefiniowanego nadawcy."""
    creds = get_creds()
    user = creds["email"]
    pwd = creds["password"]
    allowed_sender = creds["recipient"]
    
    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    
    messages = []
    try:
        # Połączenie IMAP
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, pwd)
        mail.select("inbox")
        
        # Szukanie nieprzeczytanych od Mateusza
        status, response = mail.search(None, f'(UNSEEN FROM "{allowed_sender}")')
        unread_msg_ids = response[0].split()
        
        for msg_id in unread_msg_ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            subject = email.header.decode_header(msg["Subject"])[0][0]
            if isinstance(subject, bytes): subject = subject.decode()
            
            body = ""
            attachments = []
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        body = part.get_payload(decode=True).decode()
                    elif "attachment" in content_disposition:
                        filename = part.get_filename()
                        if filename:
                            filepath = os.path.join(ATTACHMENTS_DIR, filename)
                            with open(filepath, "wb") as f:
                                f.write(part.get_payload(decode=True))
                            attachments.append(filepath)
            else:
                body = msg.get_payload(decode=True).decode()
                
            messages.append({
                "id": msg_id,
                "subject": subject,
                "body": body,
                "attachments": attachments
            })
            
        mail.logout()
    except Exception as e:
        print(f"[!] Blad IMAP: {e}")
        
    return messages

if __name__ == "__main__":
    print("[*] Test odbiornika...")
    mails = fetch_unread_emails()
    print(f"[*] Znaleziono {len(mails)} nowych maili.")
    for m in mails:
        print(f"- {m['subject']} (Zalaczniki: {len(m['attachments'])})")
