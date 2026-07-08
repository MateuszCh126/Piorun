"""Tygodniowy digest autonomii - deterministyczny (bez LLM).

Agreguje ostatnie N dni: ticki i akcje autonomii, decyzje kolejki, notatki
research, nadchodzace terminy. Zapisuje markdown do workdir; opcjonalnie
wysyla mailem. Przy okazji sprzata: rotacja starych logow + backup + prune.

Uzycie:
  python piorun.py digest              # zapis do pliku
  python piorun.py digest --email      # zapis + mail do wlasciciela
  python piorun.py digest --days 14 --no-maintenance
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import get_settings

SETTINGS = get_settings()


def _parse_iso(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_jsonl(path):
    items = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return items


def collect_digest(days=7):
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    decisions_path = SETTINGS.autonomy_state_dir / "decisions.jsonl"
    events = _read_jsonl(str(decisions_path))

    ticks = executed = queued = skipped = reminders = 0
    approvals = rejections = 0
    executed_titles = []
    for e in events:
        ts = _parse_iso(e.get("timestamp"))
        if ts is None or ts < cutoff:
            continue
        kind = e.get("kind")
        if kind == "tick":
            ticks += 1
            ex = e.get("executed", [])
            executed += len(ex)
            queued += len(e.get("queued", []))
            skipped += len(e.get("skipped", []))
            for x in ex:
                if x.get("action_type") == "send_reminder":
                    reminders += 1
                title = str(x.get("title", "")).strip()
                if title:
                    executed_titles.append(title)
        elif kind == "queue_decision":
            decision = str(e.get("decision", ""))
            if decision.startswith("APPROVED"):
                approvals += 1
            elif decision == "REJECTED":
                rejections += 1

    # Notatki research z ostatnich N dni (liczba sekcji).
    research_sections = 0
    notes_dir = SETTINGS.allowed_root / "autonomy_notes"
    if notes_dir.is_dir():
        try:
            import tools.vector_memory as vm
            splitter = vm.split_note_sections
        except Exception:
            splitter = None
        for p in notes_dir.glob("*.md"):
            try:
                file_date = datetime.strptime(p.stem, "%Y-%m-%d").date()
            except ValueError:
                continue
            if file_date < (now - timedelta(days=days)).date():
                continue
            if splitter:
                research_sections += len(splitter(p.read_text(encoding="utf-8")))

    # Terminy: nadchodzace (7 dni) i zamkniete ostatnio.
    upcoming, closed_recent = [], 0
    try:
        import tools.study_deadlines as study

        upcoming = study.week_plan()
        for d in study.list_deadlines(limit=100, include_done=True):
            if str(d.get("status")) == "DONE":
                done_at = _parse_iso(d.get("completed_at"))
                if done_at is not None and done_at >= cutoff:
                    closed_recent += 1
    except Exception:
        pass

    return {
        "days": days,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ticks": ticks,
        "executed": executed,
        "queued": queued,
        "skipped": skipped,
        "reminders": reminders,
        "approvals": approvals,
        "rejections": rejections,
        "research_sections": research_sections,
        "executed_titles": executed_titles[:15],
        "upcoming": upcoming,
        "closed_recent": closed_recent,
    }


def render_markdown(data):
    lines = [
        f"# Piorun — digest autonomii ({data['days']} dni)",
        f"_Wygenerowano: {data['generated_at']}_",
        "",
        "## Aktywność autonomii",
        f"- Ticki: **{data['ticks']}**",
        f"- Wykonane akcje: **{data['executed']}** (w tym przypomnienia: {data['reminders']})",
        f"- Zakolejkowane: {data['queued']} | pominięte (duplikaty/limity): {data['skipped']}",
        f"- Decyzje kolejki: {data['approvals']} zatwierdzeń, {data['rejections']} odrzuceń",
        f"- Nowe notatki research (sekcje): **{data['research_sections']}**",
        "",
        "## Terminy studenckie",
        f"- Zamknięte w tym okresie: **{data['closed_recent']}**",
    ]
    if data["upcoming"]:
        lines.append(f"- Nadchodzące (7 dni): **{len(data['upcoming'])}**")
        for d in data["upcoming"][:10]:
            lines.append(
                f"  - ({d.get('priority', '')}) {str(d.get('due_at', ''))[:16]} — "
                f"{d.get('subject', '')}: {d.get('title', '')}"
            )
    else:
        lines.append("- Nadchodzące (7 dni): brak")

    if data["executed_titles"]:
        lines.append("")
        lines.append("## Ostatnio wykonane")
        for t in data["executed_titles"]:
            lines.append(f"- {t}")

    lines.append("")
    return "\n".join(lines)


def build_digest(days=7, send=False, maintenance=True):
    data = collect_digest(days)
    md = render_markdown(data)

    out_path = SETTINGS.workdir / f"digest_{datetime.now().strftime('%Y%m%d')}.md"
    try:
        out_path.write_text(md, encoding="utf-8")
    except Exception as e:
        print(f"[!] Nie udalo sie zapisac digestu: {e}")

    if send:
        try:
            import core.brain as brain

            recipient = brain._get_default_recipient()
            if recipient:
                status = brain.mailer.send_email(
                    to_email=recipient,
                    subject=f"Piorun — digest autonomii {datetime.now().strftime('%d.%m.%Y')}",
                    body=md,
                )
                print(f"[*] Digest wyslany: {status}")
            else:
                print("[!] Brak odbiorcy - digest nie wyslany.")
        except Exception as e:
            print(f"[!] Wysylka digestu nie powiodla sie: {e}")

    if maintenance:
        try:
            import core.ops_runtime as ops

            rotated = ops.rotate_old_logs()
            if rotated.get("archived"):
                print(f"[*] Zarchiwizowano logi: {len(rotated['archived'])} plikow.")
            backup = ops.create_backup(include_workdir=False)
            pruned = ops.prune_backups(keep=8)
            print(f"[*] Backup: {os.path.basename(backup['backup_path'])}"
                  + (f", usunieto starych: {len(pruned)}" if pruned else ""))
        except Exception as e:
            print(f"[!] Konserwacja pominieta: {e}")

    return str(out_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tygodniowy digest autonomii Pioruna.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--email", action="store_true", help="Wyslij digest mailem do wlasciciela.")
    parser.add_argument("--no-maintenance", action="store_true", help="Pomin rotacje logow i backup.")
    args = parser.parse_args(argv)

    path = build_digest(days=args.days, send=args.email, maintenance=not args.no_maintenance)
    print(f"[OK] Digest: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
