import argparse
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.ops_runtime as ops


def _print_json(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _fmt_text(value, max_len=90):
    text = str(value or "").strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _print_queue(items):
    if not items:
        print("[autonomy] Queue is empty.")
        return
    print(f"[autonomy] Queue size: {len(items)}")
    for idx, item in enumerate(items, start=1):
        action = item.get("action", {}) if isinstance(item.get("action", {}), dict) else {}
        action_type = str(action.get("type", ""))
        title = _fmt_text(item.get("title", ""), 70)
        blocked = _fmt_text(item.get("reason_blocked", ""), 38)
        print(
            f"{idx:02d}. {item.get('id','')} | risk={item.get('risk','?')} | "
            f"conf={item.get('confidence','?')} | action={action_type} | blocked={blocked}"
        )
        if title:
            print(f"    title: {title}")


def _get_queue(limit=50):
    return ops.list_autonomy_queue(limit=limit)


def _get_queue_item_by_id(item_id, limit=500):
    for item in _get_queue(limit=limit):
        if str(item.get("id", "")).strip() == str(item_id).strip():
            return item
    return None


def _choose_next_item(limit=200):
    queue = _get_queue(limit=limit)
    if not queue:
        return None
    # Queue is append-only; first item is oldest waiting decision.
    return queue[0]


def cmd_status(_args):
    _print_json(ops.get_autonomy_state())


def cmd_queue(args):
    items = _get_queue(limit=args.limit)
    _print_queue(items)


def cmd_tick(_args):
    result = ops.run_autonomy_tick_now()
    _print_json(result)


def cmd_approve(args):
    reviewer = args.reviewer or "ops_cli"
    item = _get_queue_item_by_id(args.id)
    if item is None:
        print(f"[autonomy] Item not found: {args.id}")
        return 1
    result = ops.decide_autonomy_queue_item(item_id=args.id, decision="approve", reviewer=reviewer, reason="")
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_reject(args):
    reviewer = args.reviewer or "ops_cli"
    reason = args.reason or ""
    item = _get_queue_item_by_id(args.id)
    if item is None:
        print(f"[autonomy] Item not found: {args.id}")
        return 1
    result = ops.decide_autonomy_queue_item(item_id=args.id, decision="reject", reviewer=reviewer, reason=reason)
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_approve_next(args):
    reviewer = args.reviewer or "ops_cli"
    next_item = _choose_next_item(limit=args.limit)
    if not next_item:
        print("[autonomy] Queue is empty.")
        return 0
    item_id = str(next_item.get("id", "")).strip()
    print(f"[autonomy] Approving next item: {item_id}")
    result = ops.decide_autonomy_queue_item(item_id=item_id, decision="approve", reviewer=reviewer, reason="")
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_reject_next(args):
    reviewer = args.reviewer or "ops_cli"
    reason = args.reason or "operator_rejected"
    next_item = _choose_next_item(limit=args.limit)
    if not next_item:
        print("[autonomy] Queue is empty.")
        return 0
    item_id = str(next_item.get("id", "")).strip()
    print(f"[autonomy] Rejecting next item: {item_id}")
    result = ops.decide_autonomy_queue_item(item_id=item_id, decision="reject", reviewer=reviewer, reason=reason)
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_panel(args):
    reviewer = args.reviewer or "ops_panel"
    print("[autonomy] Interactive panel. Actions: [a]pprove, [r]eject, [s]kip, [q]uit")
    skipped_ids = set()

    while True:
        state = ops.get_autonomy_state()
        queue = _get_queue(limit=args.limit)
        print(
            f"\n[state] enabled={state.get('enabled')} queue={state.get('queue_size')} "
            f"ticks={state.get('ticks_count')} autoexec_hour={state.get('autoexec_count_this_hour')}"
        )
        if not queue:
            print("[autonomy] Queue is empty.")
            return 0

        item = None
        for candidate in queue:
            candidate_id = str(candidate.get("id", "")).strip()
            if candidate_id not in skipped_ids:
                item = candidate
                break
        if item is None:
            skipped_ids.clear()
            item = queue[0]

        item_id = str(item.get("id", "")).strip()
        action = item.get("action", {}) if isinstance(item.get("action", {}), dict) else {}
        print(f"[item] id={item_id}")
        print(f"[item] title={_fmt_text(item.get('title', ''), 120)}")
        print(
            f"[item] risk={item.get('risk')} confidence={item.get('confidence')} "
            f"blocked={_fmt_text(item.get('reason_blocked', ''), 120)}"
        )
        print(f"[item] action={json.dumps(action, ensure_ascii=False)}")

        raw = input("[panel] choose (a/r/s/q): ").strip().lower()
        if raw == "q":
            return 0
        if raw == "s":
            skipped_ids.add(item_id)
            print(f"[panel] skipped id={item_id}")
            continue
        if raw == "a":
            result = ops.decide_autonomy_queue_item(item_id=item_id, decision="approve", reviewer=reviewer, reason="")
            skipped_ids.discard(item_id)
            _print_json(result)
            continue
        if raw == "r":
            reason = input("[panel] reject reason: ").strip()
            result = ops.decide_autonomy_queue_item(
                item_id=item_id,
                decision="reject",
                reviewer=reviewer,
                reason=reason or "operator_rejected",
            )
            skipped_ids.discard(item_id)
            _print_json(result)
            continue
        print("[panel] unknown action.")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Autonomy operator CLI: queue review and approve/reject decisions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show autonomy state.")
    p_status.set_defaults(func=cmd_status)

    p_queue = sub.add_parser("queue", help="Show queued autonomy decisions.")
    p_queue.add_argument("--limit", type=int, default=20, help="How many queued items to show.")
    p_queue.set_defaults(func=cmd_queue)

    p_tick = sub.add_parser("tick", help="Run one autonomy tick now.")
    p_tick.set_defaults(func=cmd_tick)

    p_approve = sub.add_parser("approve", help="Approve a specific queue item by id.")
    p_approve.add_argument("id", help="Queue item id (AQ_...).")
    p_approve.add_argument("--reviewer", default="ops_cli", help="Reviewer tag.")
    p_approve.set_defaults(func=cmd_approve)

    p_reject = sub.add_parser("reject", help="Reject a specific queue item by id.")
    p_reject.add_argument("id", help="Queue item id (AQ_...).")
    p_reject.add_argument("--reason", default="operator_rejected", help="Reject reason.")
    p_reject.add_argument("--reviewer", default="ops_cli", help="Reviewer tag.")
    p_reject.set_defaults(func=cmd_reject)

    p_approve_next = sub.add_parser("approve-next", help="Approve the oldest queued item.")
    p_approve_next.add_argument("--limit", type=int, default=200, help="Queue window for search.")
    p_approve_next.add_argument("--reviewer", default="ops_cli", help="Reviewer tag.")
    p_approve_next.set_defaults(func=cmd_approve_next)

    p_reject_next = sub.add_parser("reject-next", help="Reject the oldest queued item.")
    p_reject_next.add_argument("--limit", type=int, default=200, help="Queue window for search.")
    p_reject_next.add_argument("--reason", default="operator_rejected", help="Reject reason.")
    p_reject_next.add_argument("--reviewer", default="ops_cli", help="Reviewer tag.")
    p_reject_next.set_defaults(func=cmd_reject_next)

    p_panel = sub.add_parser("panel", help="Interactive queue review panel.")
    p_panel.add_argument("--limit", type=int, default=50, help="Queue window to inspect.")
    p_panel.add_argument("--reviewer", default="ops_panel", help="Reviewer tag.")
    p_panel.set_defaults(func=cmd_panel)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    if isinstance(result, int):
        raise SystemExit(result)


if __name__ == "__main__":
    main()
