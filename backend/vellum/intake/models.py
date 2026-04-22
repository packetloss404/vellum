from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..models import CheckInPolicy, DossierType


class IntakeStatus(str, Enum):
    gathering = "gathering"    # still collecting the 5 fields
    committed = "committed"    # turned into a dossier
    abandoned = "abandoned"    # user bailed or stale


class IntakeMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class IntakeState(BaseModel):
    """The five fields the intake agent elicits. All Optional until complete."""
    title: Optional[str] = None
    problem_statement: Optional[str] = None
    dossier_type: Optional[DossierType] = None
    out_of_scope: list[str] = Field(default_factory=list)
    check_in_policy: Optional[CheckInPolicy] = None

    def is_complete(self) -> bool:
        return (
            self.title is not None
            and self.problem_statement is not None
            and self.dossier_type is not None
            and self.check_in_policy is not None
        )


class IntakeSession(BaseModel):
    id: str
    status: IntakeStatus = IntakeStatus.gathering
    state: IntakeState = Field(default_factory=IntakeState)
    messages: list[IntakeMessage] = Field(default_factory=list)
    dossier_id: Optional[str] = None    # set on commit
    created_at: datetime
    updated_at: datetime


# ---------- API request shapes ----------


class IntakeStart(BaseModel):
    opening_message: Optional[str] = None


class IntakeUserTurn(BaseModel):
    content: str


# ---------- intake-runtime return shape ----------


@dataclass
class IntakeTurnResult:
    intake_status: IntakeStatus
    state: IntakeState
    assistant_message: str
    dossier_id: Optional[str] = None
    error: Optional[str] = None


if __name__ == "__main__":
    from datetime import timezone

    from ..models import CheckInCadence, new_id, utc_now

    # Empty state -> not complete.
    empty_state = IntakeState()
    assert empty_state.is_complete() is False, "empty state should not be complete"

    # Fully populated state -> complete.
    full_state = IntakeState(
        title="Should we migrate from Postgres to DuckDB for analytics?",
        problem_statement=(
            "Analytics queries are saturating our primary Postgres. "
            "Evaluate whether DuckDB as a secondary store fits our workload."
        ),
        dossier_type=DossierType.decision_memo,
        out_of_scope=["OLTP migration", "vendor-managed warehouses"],
        check_in_policy=CheckInPolicy(
            cadence=CheckInCadence.weekly,
            notes="ping me Fridays with any material changes",
        ),
    )
    assert full_state.is_complete() is True, "fully populated state should be complete"

    # Build a realistic session and round-trip it through JSON.
    now = utc_now()
    session = IntakeSession(
        id=new_id("intk"),
        status=IntakeStatus.gathering,
        state=full_state,
        messages=[
            IntakeMessage(
                id=new_id("msg"),
                role="assistant",
                content="What problem are we trying to solve?",
                created_at=now,
            ),
            IntakeMessage(
                id=new_id("msg"),
                role="user",
                content="Postgres is buckling under analytics load.",
                created_at=now,
            ),
        ],
        dossier_id=None,
        created_at=now,
        updated_at=now,
    )

    payload = session.model_dump_json()
    restored = IntakeSession.model_validate_json(payload)
    assert restored == session, "session should round-trip through JSON cleanly"
    assert restored.state.is_complete() is True
    assert restored.messages[0].role == "assistant"
    assert restored.messages[1].role == "user"

    # Exercise the API request shapes and the dataclass result.
    start = IntakeStart(opening_message="I need to pick a database.")
    turn = IntakeUserTurn(content="DuckDB vs Postgres for analytics.")
    assert start.opening_message and turn.content

    result = IntakeTurnResult(
        intake_status=IntakeStatus.committed,
        state=full_state,
        assistant_message="Dossier created.",
        dossier_id=new_id("dos"),
    )
    assert result.dossier_id is not None
    assert result.error is None
    # Confirm datetimes are tz-aware (utc_now guarantees this).
    assert restored.created_at.tzinfo is not None
    _ = timezone.utc  # silence unused import if linters look

    print("intake models OK")
