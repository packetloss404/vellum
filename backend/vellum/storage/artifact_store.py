"""Artifact CRUD."""
from __future__ import annotations

from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt_str,
    _log_change,
    _row_to_artifact,
    _touch_dossier,
)


def create_artifact(
    dossier_id: str,
    data: m.ArtifactCreate,
    work_session_id: Optional[str] = None,
) -> m.Artifact:
    now = m.utc_now()
    artifact = m.Artifact(
        id=m.new_id("art"),
        dossier_id=dossier_id,
        kind=data.kind,
        title=data.title,
        content=data.content,
        intended_use=data.intended_use,
        state=data.state,
        kind_note=data.kind_note,
        supersedes=data.supersedes,
        last_updated=now,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO artifacts (id, dossier_id, kind, title, content, intended_use,
                                   state, kind_note, supersedes, last_updated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.id,
                dossier_id,
                artifact.kind.value,
                artifact.title,
                artifact.content,
                artifact.intended_use,
                artifact.state.value,
                artifact.kind_note,
                artifact.supersedes,
                _dt_str(now),
                _dt_str(now),
            ),
        )
        _log_change(
            conn, dossier_id, work_session_id, "artifact_added",
            f"Added artifact: {artifact.title}",
        )
        _touch_dossier(conn, dossier_id)
    return artifact


def get_artifact(artifact_id: str) -> Optional[m.Artifact]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    return _row_to_artifact(row) if row else None


def list_artifacts(dossier_id: str) -> list[m.Artifact]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM artifacts WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_artifact(r) for r in rows]


def update_artifact(
    dossier_id: str,
    artifact_id: str,
    patch: m.ArtifactUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Artifact]:
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM artifacts WHERE id = ? AND dossier_id = ?",
            (artifact_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        fields: list[tuple[str, object]] = []
        if patch.kind is not None:
            fields.append(("kind", patch.kind.value))
        if patch.title is not None:
            fields.append(("title", patch.title))
        if patch.content is not None:
            fields.append(("content", patch.content))
        if patch.intended_use is not None:
            fields.append(("intended_use", patch.intended_use))
        if patch.state is not None:
            fields.append(("state", patch.state.value))
        fields.append(("last_updated", _dt_str(m.utc_now())))
        set_clause = ", ".join(f"{k} = ?" for k, _ in fields)
        values = [v for _, v in fields] + [artifact_id]
        conn.execute(f"UPDATE artifacts SET {set_clause} WHERE id = ?", values)
        _log_change(
            conn, dossier_id, work_session_id, "artifact_updated",
            patch.change_note,
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    return _row_to_artifact(row)


def delete_artifact(
    dossier_id: str,
    artifact_id: str,
    work_session_id: Optional[str] = None,
) -> bool:
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM artifacts WHERE id = ? AND dossier_id = ?",
            (artifact_id, dossier_id),
        ).fetchone()
        if not existing:
            return False
        conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
        _log_change(
            conn, dossier_id, work_session_id, "artifact_deleted",
            f"Deleted artifact: {existing['title']}",
        )
        _touch_dossier(conn, dossier_id)
    return True
