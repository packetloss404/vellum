"""CRUD + lifecycle for intake sessions and their messages.

Intake is a separate concern from dossiers: a gathering conversation becomes a
dossier only on commit. These tables live alongside dossier tables but carry
no foreign-key relationship to them — the link is the optional `dossier_id`
written when status transitions to `committed`.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from .. import models as m
from ..db import connect
from .models import IntakeMessage, IntakeSession, IntakeState, IntakeStatus


def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


def _dt_str(dt: datetime) -> str:
    return dt.isoformat()


# ---------- row → model converters ----------


def _row_to_message(row: sqlite3.Row) -> IntakeMessage:
    return IntakeMessage(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        created_at=_dt(row["created_at"]),
    )


def _row_to_session(
    row: sqlite3.Row,
    messages: Optional[list[IntakeMessage]] = None,
) -> IntakeSession:
    return IntakeSession(
        id=row["id"],
        status=IntakeStatus(row["status"]),
        state=IntakeState.model_validate_json(row["state"]),
        messages=messages or [],
        dossier_id=row["dossier_id"],
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def _fetch_messages(conn: sqlite3.Connection, intake_id: str) -> list[IntakeMessage]:
    rows = conn.execute(
        "SELECT * FROM intake_messages WHERE intake_id = ? ORDER BY created_at, id",
        (intake_id,),
    ).fetchall()
    return [_row_to_message(r) for r in rows]


# ---------- CRUD ----------


def create_intake() -> IntakeSession:
    now = m.utc_now()
    session = IntakeSession(
        id=m.new_id("intk"),
        status=IntakeStatus.gathering,
        state=IntakeState(),
        messages=[],
        dossier_id=None,
        created_at=now,
        updated_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO intake_sessions (id, status, state, dossier_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.status.value,
                session.state.model_dump_json(),
                session.dossier_id,
                _dt_str(session.created_at),
                _dt_str(session.updated_at),
            ),
        )
    return session


def get_intake(intake_id: str) -> Optional[IntakeSession]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM intake_sessions WHERE id = ?", (intake_id,)
        ).fetchone()
        if not row:
            return None
        messages = _fetch_messages(conn, intake_id)
    return _row_to_session(row, messages=messages)


def list_intakes(status: Optional[IntakeStatus] = None) -> list[IntakeSession]:
    """Returns sessions without populating `messages` (keeps list views cheap)."""
    with connect() as conn:
        if status is None:
            rows = conn.execute(
                "SELECT * FROM intake_sessions ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM intake_sessions WHERE status = ? ORDER BY updated_at DESC",
                (status.value,),
            ).fetchall()
    return [_row_to_session(r) for r in rows]


def update_intake_state(intake_id: str, state: IntakeState) -> IntakeSession:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM intake_sessions WHERE id = ?", (intake_id,)
        ).fetchone()
        if not existing:
            raise KeyError(f"intake session {intake_id} not found")
        conn.execute(
            "UPDATE intake_sessions SET state = ?, updated_at = ? WHERE id = ?",
            (state.model_dump_json(), now_s, intake_id),
        )
    result = get_intake(intake_id)
    assert result is not None  # row existed above; refetch can't disappear mid-txn
    return result


def update_intake_status(
    intake_id: str,
    status: IntakeStatus,
    dossier_id: Optional[str] = None,
) -> IntakeSession:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM intake_sessions WHERE id = ?", (intake_id,)
        ).fetchone()
        if not existing:
            raise KeyError(f"intake session {intake_id} not found")
        if dossier_id is None:
            conn.execute(
                "UPDATE intake_sessions SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now_s, intake_id),
            )
        else:
            conn.execute(
                "UPDATE intake_sessions SET status = ?, dossier_id = ?, updated_at = ? WHERE id = ?",
                (status.value, dossier_id, now_s, intake_id),
            )
    result = get_intake(intake_id)
    assert result is not None
    return result


def append_intake_message(intake_id: str, role: str, content: str) -> IntakeMessage:
    now = m.utc_now()
    now_s = _dt_str(now)
    message = IntakeMessage(
        id=m.new_id("im"),
        role=role,  # trust caller: the Pydantic Literal on IntakeMessage will validate
        content=content,
        created_at=now,
    )
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM intake_sessions WHERE id = ?", (intake_id,)
        ).fetchone()
        if not existing:
            raise KeyError(f"intake session {intake_id} not found")
        conn.execute(
            """
            INSERT INTO intake_messages (id, intake_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message.id, intake_id, message.role, message.content, now_s),
        )
        conn.execute(
            "UPDATE intake_sessions SET updated_at = ? WHERE id = ?",
            (now_s, intake_id),
        )
    return message


def abandon_stale_intakes(older_than_seconds: int) -> int:
    """Mark every still-gathering session whose updated_at predates the cutoff as abandoned."""
    now = m.utc_now()
    cutoff_ts = now.timestamp() - older_than_seconds
    cutoff_iso = datetime.fromtimestamp(cutoff_ts, tz=now.tzinfo).isoformat()
    now_s = _dt_str(now)
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE intake_sessions
               SET status = 'abandoned', updated_at = ?
             WHERE status = 'gathering' AND updated_at < ?
            """,
            (now_s, cutoff_iso),
        )
        return cur.rowcount


def delete_intake(intake_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM intake_sessions WHERE id = ?", (intake_id,))
        return cur.rowcount > 0


# ---------- smoke test ----------


if __name__ == "__main__":
    import os
    import tempfile

    os.environ["VELLUM_DB_PATH"] = tempfile.mktemp(suffix=".db")

    from .. import db  # noqa: E402 — must be imported after VELLUM_DB_PATH is set

    db.init_db()

    from ..models import CheckInCadence, CheckInPolicy, DossierType

    # create → get → verify empty messages + gathering status
    s = create_intake()
    got = get_intake(s.id)
    assert got is not None
    assert got.status == IntakeStatus.gathering
    assert got.messages == []
    assert got.dossier_id is None
    assert got.state == IntakeState()

    # update state → get → verify state persisted
    new_state = IntakeState(
        title="Pick a DB",
        problem_statement="Postgres is struggling under analytics load.",
        dossier_type=DossierType.decision_memo,
        out_of_scope=["OLTP migration"],
        check_in_policy=CheckInPolicy(cadence=CheckInCadence.weekly, notes="fridays"),
    )
    update_intake_state(s.id, new_state)
    got = get_intake(s.id)
    assert got is not None
    assert got.state.title == "Pick a DB"
    assert got.state.dossier_type == DossierType.decision_memo
    assert got.state.check_in_policy is not None
    assert got.state.check_in_policy.cadence == CheckInCadence.weekly
    assert got.state.out_of_scope == ["OLTP migration"]

    # append 2 messages → get → verify chronological ordering
    m1 = append_intake_message(s.id, "assistant", "What are we solving?")
    m2 = append_intake_message(s.id, "user", "Database choice for analytics.")
    got = get_intake(s.id)
    assert got is not None
    assert len(got.messages) == 2
    assert got.messages[0].id == m1.id
    assert got.messages[1].id == m2.id
    assert got.messages[0].role == "assistant"
    assert got.messages[1].role == "user"
    assert got.messages[0].created_at <= got.messages[1].created_at

    # update status to committed → get → verify
    update_intake_status(s.id, IntakeStatus.committed, dossier_id="dos_fake123")
    got = get_intake(s.id)
    assert got is not None
    assert got.status == IntakeStatus.committed
    assert got.dossier_id == "dos_fake123"

    # list_intakes(gathering) then list_intakes(committed)
    gathering = list_intakes(IntakeStatus.gathering)
    committed = list_intakes(IntakeStatus.committed)
    assert all(x.status == IntakeStatus.gathering for x in gathering)
    assert any(x.id == s.id for x in committed)
    # list_intakes should not populate messages
    assert all(x.messages == [] for x in committed)

    # abandon_stale_intakes(0) → assert 0 (nothing in gathering right now)
    n = abandon_stale_intakes(0)
    assert n == 0, f"expected 0 abandoned, got {n}"

    # create another → abandon_stale_intakes(0) → assert 1
    s2 = create_intake()
    n = abandon_stale_intakes(0)
    assert n == 1, f"expected 1 abandoned, got {n}"
    got2 = get_intake(s2.id)
    assert got2 is not None
    assert got2.status == IntakeStatus.abandoned

    # delete → get returns None
    assert delete_intake(s.id) is True
    assert get_intake(s.id) is None
    assert delete_intake("int_nope") is False

    print("intake storage OK")
