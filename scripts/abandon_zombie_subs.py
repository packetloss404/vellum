"""abandon_zombie_subs.py — one-shot cleanup of pre-fix zombie sub-investigations.

Before day 4's sub_runtime registration fix, `spawn_sub_investigation`
fell through to a stub handler that inserted a row in state='running'
without running any sub-agent. Subs accumulated as zombies — 21 at the
time of the fix across dos_cbf0 and dos_fc07.

This script marks every `running` sub-investigation as `abandoned` with a
uniform reason. Idempotent: already-abandoned or delivered subs are
skipped. Destructive in the sense that it changes state, but reversible
(the original sub rows remain — just with state=abandoned and a
blocked_reason explaining why).

DO NOT run this while an agent is actively in flight — it would abandon
the newly-spawned sub that IS running legitimately. The script aborts
if `/api/agents/running` returns a non-empty list, unless --force.

Usage:
    python scripts/abandon_zombie_subs.py            # dry run by default
    python scripts/abandon_zombie_subs.py --commit   # actually write
    python scripts/abandon_zombie_subs.py --commit --force
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


DEFAULT_BASE = "http://127.0.0.1:8731"
ABANDON_REASON = (
    "[zombie cleanup] Pre-fix stub handler never ran a real sub-agent; "
    "row was stuck in `running` forever. Abandoning as part of day-4 "
    "remediation. Re-spawn via the main agent if this thread is still "
    "worth pursuing."
)


def fetch(url: str):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def running_sub_count_in_fleet(base: str) -> int:
    """Return the count of sub_investigations in state='running' across the fleet."""
    dossiers = fetch(f"{base}/api/dossiers")
    total = 0
    for d in dossiers:
        full = fetch(f"{base}/api/dossiers/{d['id']}")
        subs = full.get("sub_investigations") or []
        total += sum(1 for s in subs if s.get("state") == "running")
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually apply the state change. Default is dry run.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Proceed even if an agent is currently running (use with care).",
    )
    parser.add_argument(
        "--base", default=DEFAULT_BASE,
        help=f"Backend URL (default {DEFAULT_BASE})",
    )
    args = parser.parse_args()

    # Safety rail: don't abandon a sub that might be live.
    try:
        running = fetch(f"{args.base}/api/agents/running")
    except Exception as exc:
        print(f"Could not reach /api/agents/running: {exc}")
        return 2
    if running and not args.force:
        print(
            f"ABORT: {len(running)} agent task(s) currently running. "
            f"Re-run with --force to proceed anyway (risks abandoning a live sub).\n"
            f"Running: {[r.get('dossier_id') for r in running]}"
        )
        return 2

    # Import backend modules lazily — we need to bypass the API for the
    # actual state mutation because storage.abandon_sub_investigation
    # isn't exposed as an HTTP endpoint in a general form (there's
    # /sub-investigations/{id}/abandon but it requires a reason query
    # param and is designed for agent use). Writing directly via storage
    # keeps the script self-contained.
    import pathlib
    backend_dir = pathlib.Path(__file__).resolve().parent.parent / "backend"
    sys.path.insert(0, str(backend_dir))
    from vellum import storage, models as m

    dossiers = fetch(f"{args.base}/api/dossiers")
    to_abandon: list[tuple[str, str, str]] = []
    for d in dossiers:
        full = fetch(f"{args.base}/api/dossiers/{d['id']}")
        subs = full.get("sub_investigations") or []
        for s in subs:
            if s.get("state") != "running":
                continue
            title = s.get("title") or s.get("scope") or s.get("id")
            to_abandon.append((d["id"], s["id"], title))

    if not to_abandon:
        print("No zombie subs found. Nothing to do.")
        return 0

    print(f"Found {len(to_abandon)} sub(s) in `running` state:")
    for dossier_id, sub_id, title in to_abandon:
        print(f"  {sub_id}  {dossier_id}  {title[:70]}")

    if not args.commit:
        print()
        print("Dry run. Re-run with --commit to actually abandon.")
        return 0

    print()
    print("Committing abandonments...")
    ok_count = 0
    fail_count = 0
    for dossier_id, sub_id, title in to_abandon:
        try:
            result = storage.abandon_sub_investigation(
                dossier_id, sub_id, ABANDON_REASON, work_session_id=None,
            )
            if result is not None and result.state == m.SubInvestigationState.abandoned:
                ok_count += 1
                print(f"  [OK]   {sub_id}")
            else:
                fail_count += 1
                print(f"  [FAIL] {sub_id} — storage returned {result!r}")
        except Exception as exc:
            fail_count += 1
            print(f"  [FAIL] {sub_id} — {type(exc).__name__}: {exc}")

    print()
    print(f"Summary: {ok_count} abandoned, {fail_count} failed")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
