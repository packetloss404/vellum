"""Day-6 polish: sub-investigation completion reliability + delivery guard.

The day-5 live run left ``dos_83702bf49194`` with 3 sub-investigations stuck
in ``state=running`` because the sub-agent loop errored mid-turn, both the
model's ``complete_sub_investigation`` call AND the force-complete fallback
failed silently, and the main agent then went on to flip the dossier to
``delivered`` while subs were still running.

This file locks in the day-6 fix:
    * ``run_sub_investigation`` now wraps its body in an outer try/except
      that persists a ``[sub-agent errored: ...]`` completion row and
      re-raises so ``spawn_handler`` can surface the error.
    * ``spawn_handler`` catches any error, ensures the sub is NOT left in
      ``running`` (abandoning as a belt-and-suspenders fallback), and
      returns a structured error to the main agent.
    * The force-complete path writes the ``[incomplete — max_turns
      reached]`` summary via ``handlers.complete_sub_investigation``.
    * ``mark_investigation_delivered`` refuses to flip the dossier when:
        - any sub is still running
        - any needs_input is open
        - any plan_approval decision_point is open

No live LLM calls; everything mocks ``anthropic.AsyncAnthropic``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Mock helpers — mirror the shape test_sub_runtime.py uses so we stay
# consistent with the existing mocking vocabulary.
# ---------------------------------------------------------------------------


@dataclass
class _Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict | None = None


@dataclass
class _Usage:
    input_tokens: int = 10
    output_tokens: int = 5


@dataclass
class _Response:
    content: list
    stop_reason: str = "end_turn"
    usage: _Usage | None = None


def _text_block(text: str) -> _Block:
    return _Block(type="text", text=text)


def _tool_use(name: str, input_: dict, id_: str = "tu_1") -> _Block:
    return _Block(type="tool_use", name=name, input=input_, id=id_)


def _make_mock_client(responses: list[_Response]) -> AsyncMock:
    """Replay ``responses`` through ``client.messages.stream()``."""
    iterator = iter(responses)
    fallback = _Response(
        content=[_text_block("silent turn")],
        stop_reason="end_turn",
        usage=_Usage(),
    )

    def _next() -> _Response:
        try:
            return next(iterator)
        except StopIteration:
            return fallback

    def _stream(**kwargs):
        msg = _next()

        class _StreamCM:
            async def __aenter__(self):
                class _Stream:
                    async def get_final_message(self_inner):
                        return msg
                return _Stream()

            async def __aexit__(self, *exc):
                return False

        return _StreamCM()

    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.stream = _stream
    return client


def _make_raising_client(exc: Exception) -> AsyncMock:
    """Client whose ``messages.stream`` raises ``exc`` on entry."""

    def _stream(**kwargs):
        class _StreamCM:
            async def __aenter__(self_inner):
                raise exc

            async def __aexit__(self_inner, *e):
                return False

        return _StreamCM()

    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.stream = _stream
    return client


def _mk_dossier():
    from vellum import models as m, storage
    return storage.create_dossier(
        m.DossierCreate(
            title="completion-reliability test dossier",
            problem_statement="Day-6 polish.",
            dossier_type=m.DossierType.investigation,
        )
    )


# ===========================================================================
# 1. Sub-runtime outer exception handling
# ===========================================================================


def test_sub_runtime_outer_exception_persists_failure_row(fresh_db):
    """When the stream raises mid-turn, the sub row must NOT stay in running.

    Expectation: ``spawn_handler`` catches the error, returns a dict that
    surfaces it to the main agent, and storage reflects the sub as either
    ``delivered`` (with a ``[sub-agent errored: ...]`` summary) or
    ``abandoned``. Either way — not ``running``.
    """
    from vellum import models as m, storage
    from vellum.agent import sub_runtime

    dossier = _mk_dossier()
    # Ensure an active session exists so spawn_handler reuses it.
    storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    broken_client = _make_raising_client(RuntimeError("streaming exploded"))

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=broken_client,
    ):
        result = sub_runtime.spawn_handler(
            dossier.id,
            {
                "scope": "A scope that triggers the error path",
                "questions": ["Will this blow up?"],
            },
        )

    # spawn_handler must return a structured dict, not raise.
    assert isinstance(result, dict)
    assert "sub_investigation_id" in result
    sub_id = result["sub_investigation_id"]

    # The structured result surfaces the error to the main agent.
    assert result.get("terminated_without_completion") is True
    combined = (result.get("return_summary", "") + result.get("error", "")).lower()
    assert "error" in combined or "exploded" in combined, (
        f"error not surfaced in result: {result!r}"
    )

    # Crucially: the sub row is NOT stuck in running.
    sub = storage.get_sub_investigation(sub_id)
    assert sub is not None
    assert sub.state != m.SubInvestigationState.running, (
        f"sub left in running state after error: {sub!r}"
    )
    assert sub.state in (
        m.SubInvestigationState.delivered,
        m.SubInvestigationState.abandoned,
    )


# ===========================================================================
# 2. Force-complete fallback (max_turns exhausted, no completion call)
# ===========================================================================


def test_force_complete_fallback_at_max_turns(fresh_db):
    """Model never calls complete_sub_investigation → force-complete fires."""
    import asyncio

    from vellum import models as m, storage
    from vellum.agent import sub_runtime

    dossier = _mk_dossier()
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="never-completes", questions=["q?"]),
    )

    # Every turn calls log_source_consulted (a valid tool, not the exit).
    busy = _Response(
        content=[
            _tool_use(
                "log_source_consulted",
                {
                    "citation": "https://example.test",
                    "why_consulted": "keep the loop alive",
                    "what_learned": "tick",
                },
                id_="tu_busy",
            )
        ],
        stop_reason="tool_use",
        usage=_Usage(),
    )

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=_make_mock_client([busy, busy, busy, busy, busy]),
    ):
        result = asyncio.run(
            sub_runtime.run_sub_investigation(
                dossier.id, sub.id, sub.scope, sub.questions, max_turns=3,
            )
        )

    # Force-complete populated the run result.
    assert result["terminated_without_completion"] is True
    assert result["return_summary"] == "[incomplete — max_turns reached]"

    # And, critically, the sub row is delivered with the incomplete marker —
    # no longer in running. This is the day-5 bug caught in test.
    fetched = storage.get_sub_investigation(sub.id)
    assert fetched is not None
    assert fetched.state == m.SubInvestigationState.delivered
    assert fetched.return_summary == "[incomplete — max_turns reached]"


# ===========================================================================
# 3. Delivery guard — running subs
# ===========================================================================


def _seed_dossier_with_plan_drafted(status=None):
    """Helper: make a dossier and draft an investigation plan on it."""
    from vellum import models as m, storage
    dossier = _mk_dossier()
    if status is not None:
        storage.update_dossier(dossier.id, m.DossierUpdate(status=status))
    return dossier


def test_mark_delivered_refuses_while_subs_running(fresh_db):
    from vellum import models as m, storage
    from vellum.tools import handlers

    dossier = _mk_dossier()
    # Spawn a sub; it starts in running and stays there because we never
    # complete it.
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="open sub", questions=["q?"]),
    )
    assert sub.state == m.SubInvestigationState.running

    result = handlers.mark_investigation_delivered(
        dossier.id,
        {"why_enough": "I claim I'm done but I'm not."},
    )

    assert result.get("ok") is False
    assert result.get("reason") == "still_running_subs"
    assert any(s["id"] == sub.id for s in result.get("subs", []))
    assert "still running" in result.get("message", "")

    # Dossier.status must NOT be delivered.
    d = storage.get_dossier(dossier.id)
    assert d is not None
    assert d.status != m.DossierStatus.delivered


# ===========================================================================
# 4. Delivery guard — open plan_approval decision point
# ===========================================================================


def test_mark_delivered_refuses_on_open_plan_approval(fresh_db):
    from vellum import models as m, storage
    from vellum.tools import handlers

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    dp = storage.add_decision_point(
        dossier.id,
        m.DecisionPointCreate(
            title="Approve the plan?",
            options=[
                m.DecisionOption(label="Approve"),
                m.DecisionOption(label="Revise"),
            ],
            kind="plan_approval",
        ),
        session.id,
    )

    result = handlers.mark_investigation_delivered(
        dossier.id,
        {"why_enough": "Trying to ship without approval"},
    )

    assert result.get("ok") is False
    assert result.get("reason") == "open_plan_approval"
    ids = {dp_entry["id"] for dp_entry in result.get("decision_points", [])}
    assert dp.id in ids

    d = storage.get_dossier(dossier.id)
    assert d is not None
    assert d.status != m.DossierStatus.delivered


def test_mark_delivered_tolerates_open_generic_decision_point(fresh_db):
    """Generic DPs are OK to leave open — the agent may leave those for the user."""
    from vellum import models as m, storage
    from vellum.tools import handlers

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    storage.add_decision_point(
        dossier.id,
        m.DecisionPointCreate(
            title="Pick a strategy",
            options=[
                m.DecisionOption(label="Option A"),
                m.DecisionOption(label="Option B"),
            ],
            kind="generic",
        ),
        session.id,
    )

    result = handlers.mark_investigation_delivered(
        dossier.id,
        {"why_enough": "Plan done, generic choice is intentionally open."},
    )

    assert result.get("ok") is True
    d = storage.get_dossier(dossier.id)
    assert d is not None
    assert d.status == m.DossierStatus.delivered


# ===========================================================================
# 5. Delivery guard — open needs_input
# ===========================================================================


def test_mark_delivered_refuses_on_open_needs_input(fresh_db):
    from vellum import models as m, storage
    from vellum.tools import handlers

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    ni = storage.add_needs_input(
        dossier.id,
        m.NeedsInputCreate(question="What state are you in?"),
        session.id,
    )

    result = handlers.mark_investigation_delivered(
        dossier.id,
        {"why_enough": "Trying to ship while blocked on the user."},
    )

    assert result.get("ok") is False
    assert result.get("reason") == "open_needs_input"
    ids = {n["id"] for n in result.get("needs_input", [])}
    assert ni.id in ids

    d = storage.get_dossier(dossier.id)
    assert d is not None
    assert d.status != m.DossierStatus.delivered


# ===========================================================================
# 6. Delivery guard — all clear
# ===========================================================================


def test_mark_delivered_succeeds_when_clear(fresh_db):
    from vellum import models as m, storage
    from vellum.tools import handlers

    dossier = _mk_dossier()

    result = handlers.mark_investigation_delivered(
        dossier.id,
        {
            "why_enough": (
                "Covered the three core questions; one optional path "
                "intentionally left for the user."
            )
        },
    )

    assert result.get("ok") is True
    assert result.get("status") == m.DossierStatus.delivered.value

    d = storage.get_dossier(dossier.id)
    assert d is not None
    assert d.status == m.DossierStatus.delivered


def test_mark_delivered_succeeds_with_delivered_subs(fresh_db):
    """Subs in terminal states (delivered/abandoned) do not block delivery."""
    from vellum import models as m, storage
    from vellum.tools import handlers

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    # One delivered sub, one abandoned sub — neither should block.
    sub_done = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="done sub", questions=[]),
        session.id,
    )
    storage.complete_sub_investigation(
        dossier.id,
        sub_done.id,
        m.SubInvestigationComplete(
            return_summary="OK", findings_section_ids=[], findings_artifact_ids=[]
        ),
        session.id,
    )
    sub_gone = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="abandoned sub", questions=[]),
        session.id,
    )
    storage.abandon_sub_investigation(
        dossier.id, sub_gone.id, "no longer relevant", session.id,
    )

    result = handlers.mark_investigation_delivered(
        dossier.id,
        {"why_enough": "Two subs done, nothing pending."},
    )

    assert result.get("ok") is True
    d = storage.get_dossier(dossier.id)
    assert d is not None
    assert d.status == m.DossierStatus.delivered
