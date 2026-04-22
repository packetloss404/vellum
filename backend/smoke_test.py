"""Day-1 smoke test: exercises the storage + tool-handler layer end-to-end.

Run from backend/:
    python smoke_test.py

What it proves:
- Dossier CRUD works.
- Tool handlers write through to storage and emit change_log entries keyed to a
  work_session.
- "Since last visit" plan-diff semantics are correct: before the user visits,
  change_log shows everything; after visit + new changes, it shows only the new.
- Tool JSON schemas emit cleanly (day 2 will hand these to the Agent SDK).
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Use a throwaway DB so this test is idempotent and doesn't pollute the real one.
tmp = Path(tempfile.gettempdir()) / f"vellum_smoke_{int(time.time())}.db"
import os
os.environ["VELLUM_DB_PATH"] = str(tmp)

from vellum import db, models as m, storage
from vellum.tools import handlers


def hr(label: str) -> None:
    print(f"\n=== {label} ===")


def main() -> None:
    db.init_db()

    hr("create dossier")
    dossier = storage.create_dossier(
        m.DossierCreate(
            title="Credit card debt negotiation — friend's mother",
            problem_statement=(
                "Friend's mother passed away with ~$40k credit card debt across 3 accounts. "
                "No estate. Friend wants to know what percentage to open negotiations at."
            ),
            out_of_scope=["tax implications", "other inherited obligations"],
            dossier_type=m.DossierType.decision_memo,
        )
    )
    print(f"created {dossier.id} — {dossier.title}")

    hr("agent opens a work_session via tool handler")
    # Trigger session auto-start by calling a tool handler.
    result = handlers.append_reasoning(
        dossier.id,
        {"note": "Taking first pass. The user's framing assumes the debt is owed.", "tags": ["framing"]},
    )
    print(f"reasoning entry: {result['reasoning_id']}")
    session = storage.get_active_work_session(dossier.id)
    assert session and session.ended_at is None
    print(f"active work_session: {session.id} (trigger={session.trigger.value})")

    hr("agent pushes back on premise: flag_needs_input")
    ni = handlers.flag_needs_input(
        dossier.id,
        {
            "question": (
                "Before I go further: what state did your mother live in at time of death, "
                "and did she have any assets that passed into a probate estate? In many states, "
                "you as the heir owe nothing unless you co-signed — which changes the whole question."
            ),
        },
    )
    print(f"needs_input: {ni['needs_input_id']}")

    hr("agent upserts a summary section (provisional)")
    sec1 = handlers.upsert_section(
        dossier.id,
        {
            "type": "summary",
            "title": "What question are we actually answering?",
            "content": (
                "The user asked what percentage to open negotiations at. But the prior question "
                "is whether any debt is owed personally. In most US states, an unsecured debt of "
                "a deceased person dies with the estate; if the estate is empty, creditors get nothing "
                "and heirs owe nothing (unless they co-signed or live in a community-property state)."
            ),
            "state": "provisional",
            "change_note": "Reframed the question before attempting to answer it.",
            "sources": [],
            "depends_on": [],
        },
    )
    print(f"section 1: {sec1['section_id']} (state={sec1['state']})")

    hr("agent adds a finding with a source")
    sec2 = handlers.upsert_section(
        dossier.id,
        {
            "type": "finding",
            "title": "FDCPA limits on collector contact with heirs",
            "content": (
                "Under the FDCPA, debt collectors may contact a deceased person's spouse, "
                "personal representative, or executor — but not random heirs. They may not imply that "
                "an heir is personally liable for the debt when they are not."
            ),
            "state": "confident",
            "change_note": "Added FDCPA baseline.",
            "sources": [{"kind": "reasoning", "title": "FDCPA §§ 803, 805, 807 (from memory — to verify)"}],
            "depends_on": [],
        },
    )
    print(f"section 2: {sec2['section_id']} (state={sec2['state']})")

    hr("agent rules out a line of inquiry")
    ro = handlers.mark_ruled_out(
        dossier.id,
        {
            "subject": "'Zombie debt' tactic of paying a small amount to restart the statute of limitations",
            "reason": "Not applicable — the question is whether to negotiate, not whether the debt is time-barred.",
            "sources": [],
        },
    )
    print(f"ruled_out: {ro['ruled_out_id']}")

    hr("fetch dossier — should have 2 sections, 1 open question, 1 ruled_out")
    full = storage.get_dossier_full(dossier.id)
    assert full is not None
    print(f"sections: {len(full.sections)}")
    print(f"needs_input (open): {len([n for n in full.needs_input if n.answered_at is None])}")
    print(f"ruled_out: {len(full.ruled_out)}")
    print(f"reasoning entries: {len(full.reasoning_trail)}")
    print(f"work_sessions: {len(full.work_sessions)}")

    hr("plan-diff BEFORE first visit: all changes")
    changes = storage.list_change_log_since_last_visit(dossier.id)
    for c in changes:
        print(f"  {c.kind}: {c.change_note}")
    assert len(changes) >= 4

    hr("user visits the dossier — ends work_session, resets diff window")
    storage.mark_dossier_visited(dossier.id)
    session_after = storage.get_active_work_session(dossier.id)
    assert session_after is None

    hr("plan-diff AFTER visit: empty until agent does more work")
    changes = storage.list_change_log_since_last_visit(dossier.id)
    assert len(changes) == 0
    print(f"  (empty as expected — {len(changes)} entries)")

    hr("user answers needs_input → agent resumes and does more")
    storage.resolve_needs_input(
        dossier.id,
        ni["needs_input_id"],
        answer="She lived in Texas. Community-property state. She had a small bank account, no real estate, no co-signer on the cards.",
    )
    # Agent resumes — tool call auto-opens a new work_session (trigger=resume).
    handlers.update_section_state(
        dossier.id,
        {
            "section_id": sec1["section_id"],
            "new_state": "confident",
            "reason": "User confirmed Texas + no co-signer + no real estate. Community-property + surviving spouse would have complicated this, but mother was not married at death (implied).",
        },
    )

    hr("plan-diff AFTER resume: shows new resume-session changes only")
    changes = storage.list_change_log_since_last_visit(dossier.id)
    for c in changes:
        print(f"  {c.kind}: {c.change_note}")
    assert len(changes) >= 1, "agent's state_change should be in the diff since last visit"

    hr("tool schemas (what the agent will see on day 2)")
    schemas = handlers.tool_schemas()
    print(f"{len(schemas)} tools registered:")
    for s in schemas:
        print(f"  - {s['name']}")

    hr("SUCCESS")
    print(f"db: {tmp}")


if __name__ == "__main__":
    main()
