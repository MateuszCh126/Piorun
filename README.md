# Piorun ⚡ — Local Autonomous Assistant

> A privacy-first desktop assistant that runs a **local Gemma LLM** (via llama.cpp) with tool-calling,
> persistent memory and an autonomous operating loop — no cloud LLM required. Its standout feature is
> **Academic Mode**, which turns live lectures into structured notes automatically.

**Stack:** Python · llama.cpp (local Gemma, GGUF) · SQLite · WASAPI loopback · Whisper Large V3 (GPU) · Tkinter/GUI

---

## Highlights

### 🎓 Academic Mode
Captures a live lecture and produces clean notes with zero manual effort:
- **Audio capture** via WASAPI loopback (records system output, e.g. an MS Teams call)
- **Transcription** with GPU-accelerated Whisper Large V3
- **Slide capture** through screen-change detection (grabs a frame only when the slide actually changes)
- **Output**: an automatically compiled, structured HTML note joining transcript and slides

### 🤖 Autonomous operating loop
- Local **tool-calling** agent built on a customized Gemma model (email, files, calendar, web search…)
- **Autonomy supervisor** with configurable rate limits, cooldowns and de-duplication of actions
- Persistent **SQLite memory** of conversation history and tasks
- Reads a `user_profile.md` before autonomous decisions to align actions with the owner's goals

## Architecture

```
GUI / Ops API  ──►  Agent runtime (Gemma via llama.cpp, tool-calling)
                        │
                        ├─ tools/         — email, files, calendar, web, lecture capture …
                        ├─ core/          — runtime, autonomy supervisor, config, memory
                        └─ SQLite         — history, tasks
```

- `core/` — agent runtime, autonomy supervisor, settings, brain/prompt logic
- `tools/` — individual capabilities the model can call (one module per tool)
- `scripts/` — entry points and helpers
- `start_*.bat` — launchers (GUI chat, ops API, autonomy loop, server)

## Setup

```
pip install -r requirements.txt
copy .env.example .env   # i dostosuj wartości
```

> **Note:** the local model weights (`*.gguf`), llama.cpp binaries and any credential files are **not**
> included in this repository — see `.gitignore`. Download a Gemma GGUF model separately and point the
> config at it.

## Configuration

Runtime behaviour is driven by environment variables — see [`.env.example`](.env.example) for the full
list (autonomy limits, lecture screenshot interval, audio channels, etc.). Copy it to `.env` and adjust.

## CLI commands (piorun.py)

| Komenda | Działanie |
|---|---|
| `/lecture <przedmiot>` / `/stop` | start/stop nagrywania wykładu (audio + slajdy) |
| `/process [przedmiot]` | batch: transkrypcja → notatki → HTML (wznawialny, odporny na błędy) |
| `/notes` | otwiera dashboard notatek |
| `/study add\|list\|done\|week` | terminy studenckie |
| `/autonomy status\|queue\|tick\|approve\|reject` | podgląd i decyzje autonomii |
| `/resume`, `/restart`, `/tasks`, `/help`, `/exit` | sesje, zadania, pomoc |

## Tests

```
python -m pytest
```

Testy działają w pełni odizolowanym środowisku (katalogi tymczasowe przez zmienne
`PIORUN_*`) — nie dotykają prawdziwych baz ani folderu roboczego.

## Development

Plan rozwoju z etapami i kryteriami ukończenia: [`ROADMAP.md`](ROADMAP.md).
Historia zmian: [`CHANGELOG.md`](CHANGELOG.md).

## Status

Personal project exploring local-first agentic AI: running a capable assistant entirely on-device with
tool use, autonomy guardrails and a genuinely useful real-world feature (lecture capture).
