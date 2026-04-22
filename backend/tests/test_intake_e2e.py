"""End-to-end intake-agent test with a scripted mocked Anthropic client.

Drives a full intake conversation through ``IntakeAgent.process_turn`` using
a mocked ``anthropic.AsyncAnthropic`` — no network, no live model. The test
asserts that the day-3 polished intake:

1. Accumulates all four required fields via the set_* tool handlers across
   multi-turn conversation.
2. Commits the dossier with a seeded 3+ item investigation plan.
3. Returns the day-3 shape — ``intake_session_id``, ``dossier_id``,
   ``plan_seeded=True`` — and that shape propagates to the model as a
   tool_result the next turn could parse (if the agent chose to continue).
4. Leaves the intake in ``committed`` status with the dossier linked, and
   the dossier's ``investigation_plan`` populated and un-approved
   (``approved_at is None``, ``revision_count == 0``).

Additional coverage in the same style:
- ``test_e2e_commit_then_retry_after_missing_field_error`` — the model
  tries to commit prematurely, gets the ``missing`` error, recovers by
  calling the missing set_* tool, and retries successfully.
- ``test_e2e_malformed_plan_commits_dossier_with_plan_error`` — a plan
  item without ``question`` triggers ``plan_error`` but the dossier still
  commits (best-effort seeding contract).

Uses the same mock-client scaffolding as ``tests/test_runtime_v2.py``.
"""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from vellum import models as m
from vellum import storage as dossier_storage
from vellum.intake import runtime as intake_rt
from vellum.intake import storage as intake_storage
from vellum.intake.models import IntakeStatus


# ---------------------------------------------------------------------------
# Mock helpers (same shape as test_runtime_v2, adapted for intake)
# ---------------------------------------------------------------------------


def _text(s: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=s)


def _tool_use(name: str, input: dict[str, Any], id: str) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=dict(input), id=id)


def _message(
    content: list[SimpleNamespace],
    stop_reason: str = "end_turn",
    input_tokens: int = 50,
    output_tokens: int = 20,
) -> SimpleNamespace:
    """Shape of a Messages API response the intake runtime reads.

    Runtime touches: ``.content``, ``.stop_reason``.
    Intake runtime does NOT read ``.usage`` (unlike the dossier runtime),
    but we include it for forward compatibility.
    """
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


def _make_mock_client(scripted_turns: list[SimpleNamespace]) -> MagicMock:
    """Build an AsyncAnthropic-shaped mock.

    Each call to ``client.messages.create(...)`` pops the next scripted
    message. Tests inspect ``client._calls`` to confirm what was sent.
    """
    calls: list[dict[str, Any]] = []
    script = list(scripted_turns)

    async def _create(**kwargs: Any) -> SimpleNamespace:
        snap = dict(kwargs)
        if "messages" in snap:
            snap["messages"] = copy.deepcopy(snap["messages"])
        calls.append(snap)
        if not script:
            raise IndexError(
                f"mock client ran out of scripted turns at call #{len(calls)}"
            )
        return script.pop(0)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=_create)
    client._calls = calls  # type: ignore[attr-defined]
    return client


def _run(coro: Any) -> Any:
    """Sync wrapper — pytest-asyncio is not installed in this repo."""
    return asyncio.run(coro)


def _make_agent(intake_id: str, client: MagicMock) -> intake_rt.IntakeAgent:
    agent = intake_rt.IntakeAgent(intake_id=intake_id, model="mock-model")
    agent._client = client
    return agent


# ---------------------------------------------------------------------------
# Canonical plan used by the happy-path test
# ---------------------------------------------------------------------------


_CANONICAL_PLAN_ITEMS = [
    {
        "question": "Is this debt legally owed by the estate or by anyone else?",
        "rationale": "Settlement is premature if no one is on the hook.",
        "as_sub_investigation": False,
        "expected_sources": [
            "FDCPA text at 15 U.S.C. § 1692",
            "state probate code",
        ],
    },
    {
        "question": "What's the statute of limitations in the relevant state?",
        "rationale": "Expired SOL converts 'settle' into 'let it lapse'.",
        "as_sub_investigation": False,
        "expected_sources": [
            "state bar association website",
            "nolo.com statute-of-limitations chart",
        ],
    },
    {
        "question": (
            "What opening percentages do reputable settlement guides cite "
            "for unsecured CC debt in 3rd-party collections?"
        ),
        "rationale": "Anchors the opening offer if settlement is the right track.",
        "as_sub_investigation": True,
        "expected_sources": [
            "NerdWallet settlement guides",
            "CFPB guidance",
            "consumer law blog posts",
        ],
    },
]


# ---------------------------------------------------------------------------
# Happy-path: full 3-turn conversation ending with commit + plan seed
# ---------------------------------------------------------------------------


def test_e2e_full_intake_commits_dossier_and_seeds_plan(fresh_db):
    """Multi-turn intake flow: open intake → three user turns driving the
    agent through set_* calls → final turn fires commit_intake with a
    3-item plan → dossier + plan persist, intake status=committed."""
    session = intake_storage.create_intake()
    intake_id = session.id

    # --- Turn 1: user describes the problem.
    # Agent reacts by calling set_problem_statement + set_title, then
    # asks about dossier_type in prose, then ends the turn.
    turn1_tools = _message(
        [
            _tool_use(
                "set_problem_statement",
                {
                    "problem_statement": (
                        "Friend's mother passed with ~$40k credit card debt "
                        "across three accounts and no estate. Figure out "
                        "the opening settlement percentage."
                    ),
                },
                id="tu_ps_1",
            ),
            _tool_use(
                "set_title",
                {"title": "Negotiate deceased mother's credit card debt"},
                id="tu_title_1",
            ),
        ],
        stop_reason="tool_use",
    )
    turn1_end = _message(
        [
            _text(
                "Got it — sounds like a decision memo (you're weighing an "
                "opening offer). Is that the right frame, or does this feel "
                "more like an investigation first?"
            )
        ],
        stop_reason="end_turn",
    )

    # --- Turn 2: user confirms decision_memo, says out_of_scope is empty,
    # wants daily check-ins. Agent calls three set_* tools and asks one
    # last confirmation before commit.
    turn2_tools = _message(
        [
            _tool_use(
                "set_dossier_type",
                {"dossier_type": "decision_memo"},
                id="tu_dt_2",
            ),
            _tool_use(
                "set_out_of_scope",
                {"items": []},
                id="tu_oos_2",
            ),
            _tool_use(
                "set_check_in_policy",
                {"cadence": "daily"},
                id="tu_cip_2",
            ),
        ],
        stop_reason="tool_use",
    )
    turn2_end = _message(
        [_text("Ready to open the dossier — anything to add first?")],
        stop_reason="end_turn",
    )

    # --- Turn 3: user says go. Agent fires commit_intake with plan, then
    # tells the user in prose.
    turn3_commit = _message(
        [
            _tool_use(
                "commit_intake",
                {
                    "plan_items": _CANONICAL_PLAN_ITEMS,
                    "plan_rationale": (
                        "Check if owed, then if timely, then how to price it."
                    ),
                },
                id="tu_commit_3",
            ),
        ],
        stop_reason="tool_use",
    )
    turn3_end = _message(
        [_text("Dossier open — the agent's picking it up now.")],
        stop_reason="end_turn",
    )

    scripted = [turn1_tools, turn1_end, turn2_tools, turn2_end, turn3_commit, turn3_end]
    client = _make_mock_client(scripted)
    agent = _make_agent(intake_id, client)

    # --- Turn 1
    r1 = _run(
        agent.process_turn(
            "Helping a friend — her mom passed with ~$40k in credit card debt, "
            "no estate. What should she offer the collectors?"
        )
    )
    assert r1.error is None, r1.error
    assert r1.intake_status == IntakeStatus.gathering
    assert r1.state.problem_statement is not None
    assert r1.state.title is not None
    assert r1.state.dossier_type is None  # not set yet
    assert r1.assistant_message.startswith("Got it")

    # --- Turn 2
    r2 = _run(agent.process_turn("Decision memo works. No exclusions. Daily check-ins."))
    assert r2.error is None, r2.error
    assert r2.intake_status == IntakeStatus.gathering  # not yet committed
    assert r2.state.is_complete()  # all 4 required fields now populated
    assert r2.state.dossier_type == m.DossierType.decision_memo
    assert r2.state.check_in_policy is not None
    assert r2.state.check_in_policy.cadence == m.CheckInCadence.daily

    # --- Turn 3
    r3 = _run(agent.process_turn("Go."))
    assert r3.error is None, r3.error
    assert r3.intake_status == IntakeStatus.committed
    assert r3.dossier_id is not None
    assert r3.assistant_message.startswith("Dossier open")

    # --- Verify persistence: dossier + plan wired up correctly.
    dossier = dossier_storage.get_dossier(r3.dossier_id)
    assert dossier is not None
    assert dossier.title.startswith("Negotiate")
    assert dossier.dossier_type == m.DossierType.decision_memo
    assert dossier.check_in_policy.cadence == m.CheckInCadence.daily

    plan = dossier.investigation_plan
    assert plan is not None, "plan should have been seeded on commit"
    assert len(plan.items) == 3
    assert plan.items[0].question.startswith("Is this debt")
    assert plan.items[2].as_sub_investigation is True
    assert plan.rationale.startswith("Check if owed")
    # Intake must NOT auto-approve; it's a draft for the first agent turn.
    assert plan.approved_at is None
    assert plan.revision_count == 0
    assert plan.drafted_at is not None

    # --- Verify the intake's transcript has 6 messages total
    # (3 user + 3 assistant).
    final_intake = intake_storage.get_intake(intake_id)
    assert final_intake is not None
    assert final_intake.status == IntakeStatus.committed
    assert final_intake.dossier_id == r3.dossier_id
    user_msgs = [msg for msg in final_intake.messages if msg.role == "user"]
    asst_msgs = [msg for msg in final_intake.messages if msg.role == "assistant"]
    assert len(user_msgs) == 3
    assert len(asst_msgs) == 3

    # --- Verify the commit_intake tool_result surfaced the day-3 shape
    # back to the model (it lives in the NEXT model call's messages list,
    # i.e. the final end_turn call).
    final_call_messages = client._calls[-1]["messages"]
    tool_result_msg = next(
        msg for msg in reversed(final_call_messages)
        if msg["role"] == "user"
        and isinstance(msg["content"], list)
        and any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in msg["content"]
        )
    )
    commit_tr = next(
        b for b in tool_result_msg["content"]
        if isinstance(b, dict)
        and b.get("type") == "tool_result"
        and b.get("tool_use_id") == "tu_commit_3"
    )
    # Content is JSON — the model sees a string. Check the expected keys
    # are in the serialized payload.
    tr_content = commit_tr["content"]
    assert "intake_session_id" in tr_content
    assert "dossier_id" in tr_content
    assert '"plan_seeded": true' in tr_content


# ---------------------------------------------------------------------------
# Recovery path: premature commit → missing-field error → retry
# ---------------------------------------------------------------------------


def test_e2e_commit_then_retry_after_missing_field_error(fresh_db):
    """Agent tries to commit before dossier_type is set; gets the missing-
    fields error; on the same turn it recovers by calling set_dossier_type,
    then retries commit_intake successfully."""
    session = intake_storage.create_intake()
    intake_id = session.id

    # Prepopulate three of four required fields so only dossier_type is missing.
    from vellum.intake.models import IntakeState
    state = IntakeState(
        title="Pick an analytics sidecar",
        problem_statement="Postgres is saturating under analytics load.",
        out_of_scope=[],
        check_in_policy=m.CheckInPolicy(cadence=m.CheckInCadence.weekly),
    )
    intake_storage.update_intake_state(intake_id, state)

    # Turn: agent (mistakenly) tries commit first, gets error, then recovers.
    turn_premature_commit = _message(
        [
            _tool_use("commit_intake", {}, id="tu_commit_premature"),
        ],
        stop_reason="tool_use",
    )
    turn_recovery = _message(
        [
            _tool_use(
                "set_dossier_type",
                {"dossier_type": "decision_memo"},
                id="tu_dt_recovery",
            ),
            _tool_use(
                "commit_intake",
                {},
                id="tu_commit_retry",
            ),
        ],
        stop_reason="tool_use",
    )
    turn_end = _message(
        [_text("Dossier's open.")],
        stop_reason="end_turn",
    )

    scripted = [turn_premature_commit, turn_recovery, turn_end]
    client = _make_mock_client(scripted)
    agent = _make_agent(intake_id, client)

    result = _run(agent.process_turn("Go ahead and open it."))
    assert result.error is None, result.error
    assert result.intake_status == IntakeStatus.committed
    assert result.dossier_id is not None

    # The first commit's tool_result should be the recoverable error shape.
    # Look at the SECOND model call's messages — that call contains the
    # tool_result for the first commit_premature.
    second_call_messages = client._calls[1]["messages"]
    premature_tr = _find_tool_result(second_call_messages, "tu_commit_premature")
    assert premature_tr is not None
    # It's a JSON blob the model sees as text.
    assert "missing" in premature_tr["content"]
    assert "dossier_type" in premature_tr["content"]
    assert "intake_session_id" in premature_tr["content"]

    # The second commit's tool_result should be the happy-path shape.
    third_call_messages = client._calls[2]["messages"]
    retry_tr = _find_tool_result(third_call_messages, "tu_commit_retry")
    assert retry_tr is not None
    assert "dossier_id" in retry_tr["content"]
    assert '"plan_seeded": false' in retry_tr["content"]


# ---------------------------------------------------------------------------
# Malformed plan: dossier still commits, plan_error surfaced.
# ---------------------------------------------------------------------------


def test_e2e_malformed_plan_commits_dossier_with_plan_error(fresh_db):
    """If the agent passes a malformed plan item (missing ``question``), the
    dossier still commits and ``plan_error`` lands in the tool_result. The
    dossier's investigation_plan is None (no seeded plan)."""
    session = intake_storage.create_intake()
    intake_id = session.id

    from vellum.intake.models import IntakeState
    state = IntakeState(
        title="Pick an analytics sidecar",
        problem_statement="Postgres is saturating under analytics load.",
        dossier_type=m.DossierType.decision_memo,
        out_of_scope=[],
        check_in_policy=m.CheckInPolicy(cadence=m.CheckInCadence.weekly),
    )
    intake_storage.update_intake_state(intake_id, state)

    commit_turn = _message(
        [
            _tool_use(
                "commit_intake",
                {
                    "plan_items": [
                        # Missing required "question" field.
                        {"rationale": "no question", "expected_sources": ["web"]},
                    ],
                    "plan_rationale": "bad plan",
                },
                id="tu_commit_bad",
            ),
        ],
        stop_reason="tool_use",
    )
    end_turn = _message(
        [_text("Dossier's open; the agent will draft a plan on its first turn.")],
        stop_reason="end_turn",
    )

    client = _make_mock_client([commit_turn, end_turn])
    agent = _make_agent(intake_id, client)

    result = _run(agent.process_turn("Go."))
    assert result.error is None
    assert result.intake_status == IntakeStatus.committed
    assert result.dossier_id is not None

    # Dossier exists; plan is None (best-effort seeding failed gracefully).
    dossier = dossier_storage.get_dossier(result.dossier_id)
    assert dossier is not None
    assert dossier.investigation_plan is None

    # plan_error surfaced in the tool_result for the model's benefit.
    second_call_messages = client._calls[1]["messages"]
    commit_tr = _find_tool_result(second_call_messages, "tu_commit_bad")
    assert commit_tr is not None
    assert "plan_error" in commit_tr["content"]
    assert "dossier_id" in commit_tr["content"]
    assert '"plan_seeded": false' in commit_tr["content"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_tool_result(
    messages: list[dict[str, Any]], tool_use_id: str
) -> dict[str, Any] | None:
    """Scan a messages list for the tool_result block matching tool_use_id."""
    for msg in messages:
        if msg["role"] != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_result"
                and block.get("tool_use_id") == tool_use_id
            ):
                return block
    return None
