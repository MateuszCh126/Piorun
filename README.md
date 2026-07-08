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
copy .env.example .env   # then adjust the values
```

> **Note:** the local model weights (`*.gguf`), llama.cpp binaries and any credential files are **not**
> included in this repository — see `.gitignore`. Download a Gemma GGUF model separately and point the
> config at it.

## Configuration

Runtime behaviour is driven by environment variables — see [`.env.example`](.env.example) for the full
list (autonomy limits, lecture screenshot interval, audio channels, etc.). Copy it to `.env` and adjust.

## CLI commands (piorun.py)

| Command | What it does |
|---|---|
| `/lecture <subject>` / `/stop` | start/stop lecture recording (audio + slides) |
| `/process [subject]` | batch: transcription → notes → HTML (resumable, error-tolerant) |
| `/notes` | opens the notes dashboard |
| `/study add\|list\|done\|week` | study deadlines |
| `/autonomy status\|queue\|tick\|approve\|reject` | inspect and decide on autonomy actions |
| `/recall <phrase>` | semantic search across lecture notes, research and conversations |
| `/resume`, `/restart`, `/tasks`, `/help`, `/exit` | sessions, tasks, help |

## Vector memory (recall)

Piorun keeps a semantic long-term memory (chromadb + multilingual embeddings,
fully local): lecture notes, autonomy research and conversation summaries are
indexed automatically, and the model gets a `recall` tool. Design and rationale:
[`docs/vector-memory-design.md`](docs/vector-memory-design.md).

```
python scripts/reindex_memory.py --all     # backfill existing data
```

Kill switch: `PIORUN_MEMORY_RECALL_ENABLED=false` in `.env`.

## Tests

```
python -m pytest
```

Tests run in a fully isolated environment (temp directories via `PIORUN_*`
variables) — they never touch real databases or the working folder.

## Development

Staged development plan with completion criteria: [`ROADMAP.md`](ROADMAP.md).
Change history: [`CHANGELOG.md`](CHANGELOG.md).

## Status

Personal project exploring local-first agentic AI: running a capable assistant entirely on-device with
tool use, autonomy guardrails and a genuinely useful real-world feature (lecture capture).
