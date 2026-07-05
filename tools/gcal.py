import os.path
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

# Zakresy uprawnień (Read/Write)
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Ścieżki konfiguracyjne w izolowanym folderze .piorun
SETTINGS = get_settings()
TOKEN_PATH = str(SETTINGS.token_path)
CREDENTIALS_PATH = str(SETTINGS.gcal_credentials_path)

def get_calendar_service():
    """Obsługuje autoryzację i zwraca obiekt serwisu Google Calendar."""
    creds = None
    # Sprawdzamy czy mamy już token sesji
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    # Jeśli nie ma tokena lub jest niekatywny - logujemy się
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError("Brak pliku credentials.json! Pobierz go z Google Cloud Console.")
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Zapisujemy token na przyszłość
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

def list_upcoming_events(max_results=10):
    """Pobiera nadchodzące wydarzenia z kalendarza."""
    try:
        service = get_calendar_service()
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=max_results, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            return "Brak nadchodzących wydarzeń."

        output = "Nadchodzące wydarzenia:\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            output += f"- [{start}] {event.get('summary')}\n"
        return output

    except Exception as e:
        return f"Błąd kalendarza: {str(e)}"

def add_calendar_event(summary, start_time_iso, description="Dopisane przez Pioruna ⚡", location="Hybrid"):
    """Dodaje nowe wydarzenie do kalendarza."""
    try:
        service = get_calendar_service()
        
        # Obliczamy koniec (domyślnie 1h później)
        start = datetime.datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
        end = start + datetime.timedelta(hours=1)
        
        event = {
            'summary': summary,
            'location': location,
            'description': description,
            'start': {'dateTime': start.isoformat(), 'timeZone': 'Europe/Warsaw'},
            'end': {'dateTime': end.isoformat(), 'timeZone': 'Europe/Warsaw'},
        }

        event = service.events().insert(calendarId='primary', body=event).execute()
        return f"Sukces! Wydarzenie dodane: {event.get('htmlLink')}"

    except Exception as e:
        return f"Błąd podczas dodawania wydarzenia: {str(e)}"


# Kompatybilność wsteczna dla starszych wywołań w kodzie.
def get_events(max_results=10):
    return list_upcoming_events(max_results=max_results)


def add_event(summary, start_time, description=""):
    return add_calendar_event(summary=summary, start_time_iso=start_time, description=description)
