# Piorun z telefonu (kanał mobilny)

Cel: z telefonu widzieć stan autonomii, dostawać powiadomienia i zatwierdzać/
odrzucać pozycje z kolejki — **bez wystawiania czegokolwiek na publiczny
internet i bez wysyłania danych przez usługi trzecie**.

Zasada: Piorun zostaje local-first. Telefon łączy się z panelem działającym
na Twoim komputerze przez **prywatną sieć Tailscale** (WireGuard), a dostęp
chroni **token**. Powiadomienia idą **e-mailem** (już istnieją: przypomnienia
o terminach i tygodniowy digest) — telefon wypushuje je przez aplikację poczty.

## Architektura

```
Telefon (apka Tailscale)  ──prywatny VPN──►  Komputer: panel Pioruna (localhost)
        │                                          POST /autonomy/decision (token)
        └── powiadomienia: e-mail (Gmail push) ◄── reminders + digest
```

- **Podgląd + akcje**: panel www (`tools/ops_api_server.py`, strona `/`).
- **Powiadomienia**: istniejące maile (przypomnienia < 48 h, tygodniowy digest).
- **Bezpieczeństwo**: prywatna sieć (nic publicznego) + token na endpointach.

## Konfiguracja krok po kroku

### 1. Token (obowiązkowo przed wystawieniem na sieć)

Wygeneruj długi losowy token i wpisz do `.env`:

```
PIORUN_OPS_API_TOKEN=<40+ losowych znaków, np. z menedżera haseł>
```

Bez tokenu serwer działa tylko sensownie na `127.0.0.1`; przy nasłuchu na sieć
bez tokenu wypisze głośne ostrzeżenie (każdy w sieci mógłby zatwierdzać akcje).

### 2. Tailscale (darmowy, na kompie i telefonie)

1. Zainstaluj Tailscale na komputerze i zaloguj się (ten sam konto = tailnet).
2. Zainstaluj Tailscale na telefonie i zaloguj się tym samym kontem.
3. Sprawdź adres Tailscale komputera (np. `100.101.102.103`) w aplikacji.

### 3. Nasłuch panelu na interfejsie Tailscale

W `.env` ustaw host na adres Tailscale komputera (NIE `0.0.0.0`, żeby nie
wystawiać na całą lokalną sieć):

```
PIORUN_OPS_API_HOST=100.101.102.103
PIORUN_OPS_API_PORT=8787
```

Uruchom serwer: `start_ops_api.bat` (albo `python tools/ops_api_server.py`).

### 4. Wejście z telefonu

W przeglądarce telefonu (Tailscale włączony) otwórz:

```
http://100.101.102.103:8787/?token=<TWÓJ_TOKEN>
```

Token zapisze się w przeglądarce (localStorage) i zniknie z paska adresu —
kolejnym razem wystarczy `http://100.101.102.103:8787/`. Dodaj do ekranu
głównego jak apkę. Panel jest responsywny (duże przyciski dotykowe).

## Co panel umie

- **Podgląd**: autonomia on/off, rozmiar kolejki, liczba ticków, akcje/h, ostatni tick.
- **Kolejka**: każda pozycja z akcją/pewnością/blokadą + przyciski **Zatwierdź** / **Odrzuć**.
- **Uruchom tick teraz** — ręczne wywołanie iteracji autonomii.

## Powiadomienia

Bez nowej usługi. Piorun już wysyła maile do właściciela:
- **Przypomnienia o terminach** (`PIORUN_AUTONOMY_REMINDER_HOURS`, domyślnie 48 h).
- **Tygodniowy digest** (`python piorun.py digest --email`, najlepiej z harmonogramu).

Telefon z aplikacją Gmail wypushuje je jak powiadomienia. Treść zostaje w Twojej
poczcie — nic nie idzie przez Telegram/Pushover itp.

## Świadome ograniczenia (bezpieczeństwo)

- **Brak pełnego czatu z telefonu.** Panel celowo udostępnia tylko podgląd +
  approve/reject/tick, nie dowolne komendy do agenta (mail/pliki). To ogranicza
  skutki ewentualnego przejęcia sesji.
- **Zero publicznej ekspozycji.** Dostęp tylko przez prywatny tailnet; nie
  otwieraj portu na routerze ani nie używaj `0.0.0.0` bez świadomej decyzji.
- **Token to sekret.** Trzymaj w `.env` (jest w `.gitignore`), nie commituj.
