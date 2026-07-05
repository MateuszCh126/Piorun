import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()
CREDENTIALS_PATH = str(SETTINGS.agent_credentials_path)

from email.mime.base import MIMEBase
from email import encoders

def send_email(to_email, subject, body, attachment_path=None):
    """Wysyła e-mail, opcjonalnie z załącznikiem."""
    if not os.path.exists(CREDENTIALS_PATH):
        return "Błąd: Brak pliku agent_credentials.json."
    
    try:
        with open(CREDENTIALS_PATH, 'r') as f:
            creds = json.load(f)
            sender_email = creds.get("email")
            app_password = creds.get("password")
            
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Dodawanie załącznika
        if attachment_path and os.path.exists(attachment_path):
            filename = os.path.basename(attachment_path)
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename= {filename}")
                msg.attach(part)

        smtp_server = "smtp.gmail.com"
        smtp_port = 587

        with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(sender_email, app_password)
            server.send_message(msg)

        return f"E-mail z załącznikiem wysłany na {to_email}."
    except Exception as e:
        return f"Błąd: {str(e)}"

if __name__ == "__main__":
    # Test (wymaga pliku credentials)
    print(send_email("test@example.com", "Test Agenta", "Cześć, to testowy raport."))
