"""CRUD + aggregate reads for dossiers and their child collections.

All mutations that affect a dossier's visible state append to change_log when a
work_session_id is supplied. Storage functions never emit prose to users — the
only user-visible surface is what's written into these tables.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Optional

from pydantic import TypeAdapter

from . import models as m
from .db import connect


# TypeAdapters for list[PydanticModel] round-trips.
_SourceList = TypeAdapter(list[m.Source])
_OptionList = TypeAdapter(list[m.DecisionOption])


# ---------- Tool-markup sanitizer ----------
#
# The model occasionally falls back to XML-style tool-call formatting
# (`<parameter name="...">value</parameter>`, `<invoke name="...">`,
# `</function_calls>`, or bare `</field_name>` tags) and stuffs that
# markup *inside a string argument* of a legitimate JSON tool call. We
# end up with literal XML noise in debrief / working-theory / section
# bodies. Vellum's content contract is plaintext + markdown only, so
# stripping these patterns is safe and idempotent — users never write
# literal `<parameter>` or `</invoke>` in their own paste content.
#
# Applied on BOTH read and write: write prevents future pollution, read
# cleans existing polluted rows without a data migration.
_TOOL_MARKUP_RE = re.compile(
    r"""
    # Explicit tool-call tags, any attributes, any case.
    <\/?\s*(?:parameter|invoke|function_calls|tool_use|answer|thinking|result)
      (?:\s[^>]*)?>
    |
    # Bare closing tags whose name looks like a tool parameter
    # (lowercase + underscores). `</what_i_did>`, `</recommendation>`, etc.
    # We only match closers to avoid eating angle-bracket math / emoticons
    # like "<3" or comparison operators in markdown.
    <\/[a-z_][a-z0-9_]*>
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def _strip_tool_markup(text: Optional[str]) -> Optional[str]:
    """Remove stray XML-style tool-call markup from a prose field.

    Idempotent. Safe to apply repeatedly. Returns the input unchanged
    when it's None or contains no markup.
    """
    if not text:
        return text
    cleaned = _TOOL_MARKUP_RE.sub("", text)
    # Collapse the whitespace the tag-stripping can leave behind
    # (`</what_i_did>\n<parameter name="what_i_found">` → `\n`).
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() if cleaned != text else cleaned


def _strip_tool_markup_list(items: Optional[list[str]]) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    for v in items:
        if isinstance(v, str):
            cleaned = _strip_tool_markup(v)
            if cleaned:
                out.append(cleaned)
        else:
            out.append(v)
    return out


def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


def _dt_str(dt: datetime) -> str:
    return dt.isoformat()


def _json_list(text: str) -> list:
    return json.loads(text) if text else []


# ---------- row → model converters ----------


def _row_to_dossier(row: sqlite3.Row) -> m.Dossier:
    debrief_json = row["debrief"]
    plan_json = row["investigation_plan"]
    theory_json = _row_get(row, "working_theory")
    pc_json = _row_get(row, "premise_challenge")

    debrief = m.Debrief.model_validate_json(debrief_json) if debrief_json else None
    if debrief is not None:
        # Strip any XML-style tool markup that the model polluted into
        # debrief fields. Idempotent — harmless to apply repeatedly.
        debrief = debrief.model_copy(update={
            "what_i_did": _strip_tool_markup(debrief.what_i_did) or "",
            "what_i_found": _strip_tool_markup(debrief.what_i_found) or "",
            "what_you_should_do_next": _strip_tool_markup(debrief.what_you_should_do_next) or "",
            "what_i_couldnt_figure_out": _strip_tool_markup(debrief.what_i_couldnt_figure_out) or "",
        })

    working_theory = (
        m.WorkingTheory.model_validate_json(theory_json) if theory_json else None
    )
    if working_theory is not None:
        working_theory = working_theory.model_copy(update={
            "recommendation": _strip_tool_markup(working_theory.recommendation) or "",
            "why": _strip_tool_markup(working_theory.why) or "",
            "what_would_change_it": _strip_tool_markup(working_theory.what_would_change_it) or "",
            "unresolved_assumptions": _strip_tool_markup_list(working_theory.unresolved_assumptions),
        })

    premise_challenge = (
        m.PremiseChallenge.model_validate_json(pc_json) if pc_json else None
    )
    if premise_challenge is not None:
        premise_challenge = premise_challenge.model_copy(update={
            "original_question": _strip_tool_markup(premise_challenge.original_question) or "",
            "hidden_assumptions": _strip_tool_markup_list(premise_challenge.hidden_assumptions),
            "why_answering_now_is_risky": _strip_tool_markup(premise_challenge.why_answering_now_is_risky) or "",
            "safer_reframe": _strip_tool_markup(premise_challenge.safer_reframe) or "",
            "required_evidence_before_answering": _strip_tool_markup_list(premise_challenge.required_evidence_before_answering),
        })

    return m.Dossier(
        id=row["id"],
        title=row["title"],
        problem_statement=row["problem_statement"],
        out_of_scope=_json_list(row["out_of_scope"]),
        dossier_type=m.DossierType(row["dossier_type"]),
        status=m.DossierStatus(row["status"]),
        check_in_policy=m.CheckInPolicy.model_validate_json(row["check_in_policy"]),
        debrief=debrief,
        investigation_plan=(
            m.InvestigationPlan.model_validate_json(plan_json) if plan_json else None
        ),
        working_theory=working_theory,
        premise_challenge=premise_challenge,
        last_visited_at=_dt(row["last_visited_at"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def _row_to_next_action(row: sqlite3.Row) -> m.NextAction:
    return m.NextAction(
        id=row["id"],
        dossier_id=row["dossier_id"],
        action=row["action"],
        rationale=row["rationale"],
        priority=int(row["priority"]),
        completed=bool(row["completed"]),
        completed_at=_dt(row["completed_at"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_section(row: sqlite3.Row) -> m.Section:
    return m.Section(
        id=row["id"],
        dossier_id=row["dossier_id"],
        type=m.SectionType(row["type"]),
        title=_strip_tool_markup(row["title"]) or "",
        content=_strip_tool_markup(row["content"]) or "",
        state=m.SectionState(row["state"]),
        order=row["order"],
        change_note=_strip_tool_markup(row["change_note"]) or "",
        sources=_SourceList.validate_json(row["sources"]),
        depends_on=_json_list(row["depends_on"]),
        last_updated=_dt(row["last_updated"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_needs_input(row: sqlite3.Row) -> m.NeedsInput:
    return m.NeedsInput(
        id=row["id"],
        dossier_id=row["dossier_id"],
        question=row["question"],
        blocks_section_ids=_json_list(row["blocks_section_ids"]),
        created_at=_dt(row["created_at"]),
        answered_at=_dt(row["answered_at"]),
        answer=row["answer"],
    )


def _row_to_decision_point(row: sqlite3.Row) -> m.DecisionPoint:
    # Gracefully handle legacy rows that predate the `kind` column.
    kind = row["kind"] if "kind" in row.keys() else "generic"
    return m.DecisionPoint(
        id=row["id"],
        dossier_id=row["dossier_id"],
        title=row["title"],
        options=_OptionList.validate_json(row["options"]),
        recommendation=row["recommendation"],
        blocks_section_ids=_json_list(row["blocks_section_ids"]),
        kind=kind or "generic",
        created_at=_dt(row["created_at"]),
        resolved_at=_dt(row["resolved_at"]),
        chosen=row["chosen"],
    )


def _row_to_reasoning(row: sqlite3.Row) -> m.ReasoningTrailEntry:
    return m.ReasoningTrailEntry(
        id=row["id"],
        dossier_id=row["dossier_id"],
        work_session_id=row["work_session_id"],
        note=row["note"],
        tags=_json_list(row["tags"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_ruled_out(row: sqlite3.Row) -> m.RuledOut:
    return m.RuledOut(
        id=row["id"],
        dossier_id=row["dossier_id"],
        subject=row["subject"],
        reason=row["reason"],
        sources=_SourceList.validate_json(row["sources"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_work_session(row: sqlite3.Row) -> m.WorkSession:
    end_reason_raw = _row_get(row, "end_reason")
    end_reason = m.WorkSessionEndReason(end_reason_raw) if end_reason_raw else None
    return m.WorkSession(
        id=row["id"],
        dossier_id=row["dossier_id"],
        started_at=_dt(row["started_at"]),
        ended_at=_dt(row["ended_at"]),
        trigger=m.WorkSessionTrigger(row["trigger"]),
        token_budget_used=row["token_budget_used"],
        input_tokens=_row_get(row, "input_tokens") or 0,
        output_tokens=_row_get(row, "output_tokens") or 0,
        cost_usd=_row_get(row, "cost_usd") or 0.0,
        end_reason=end_reason,
    )


def _row_get(row: sqlite3.Row, key: str, default=None):
    """Tolerant column accessor — returns default when the column is missing.

    Lets _row_to_* helpers read columns added via ensure_columns even on rows
    fetched from older connections that didn't see the ALTER TABLE pass.
    """
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _row_to_change(row: sqlite3.Row) -> m.ChangeLogEntry:
    return m.ChangeLogEntry(
        id=row["id"],
        dossier_id=row["dossier_id"],
        work_session_id=row["work_session_id"],
        section_id=row["section_id"],
        kind=row["kind"],
        change_note=row["change_note"],
        created_at=_dt(row["created_at"]),
    )


# ---------- internal helpers ----------


def _touch_dossier(conn: sqlite3.Connection, dossier_id: str) -> None:
    conn.execute(
        "UPDATE dossiers SET updated_at = ? WHERE id = ?",
        (_dt_str(m.utc_now()), dossier_id),
    )


def _log_change(
    conn: sqlite3.Connection,
    dossier_id: str,
    work_session_id: Optional[str],
    kind: m.ChangeKind,
    change_note: str,
    section_id: Optional[str] = None,
) -> None:
    if not work_session_id:
        return
    conn.execute(
        """
        INSERT INTO change_log (id, dossier_id, work_session_id, section_id, kind, change_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            m.new_id("chg"),
            dossier_id,
            work_session_id,
            section_id,
            kind,
            change_note,
            _dt_str(m.utc_now()),
        ),
    )


# ---------- Dossier ----------


def create_dossier(data: m.DossierCreate) -> m.Dossier:
    now = m.utc_now()
    dossier = m.Dossier(
        id=m.new_id("dos"),
        title=data.title,
        problem_statement=data.problem_statement,
        out_of_scope=data.out_of_scope,
        dossier_type=data.dossier_type,
        status=m.DossierStatus.active,
        check_in_policy=data.check_in_policy,
        created_at=now,
        updated_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO dossiers (id, title, problem_statement, out_of_scope, dossier_type,
                                  status, check_in_policy, debrief, investigation_plan,
                                  created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dossier.id,
                dossier.title,
                dossier.problem_statement,
                json.dumps(dossier.out_of_scope),
                dossier.dossier_type.value,
                dossier.status.value,
                dossier.check_in_policy.model_dump_json(),
                None,
                None,
                _dt_str(dossier.created_at),
                _dt_str(dossier.updated_at),
            ),
        )
    return dossier


def get_dossier(dossier_id: str) -> Optional[m.Dossier]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
    return _row_to_dossier(row) if row else None


def list_dossiers() -> list[m.Dossier]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM dossiers ORDER BY updated_at DESC").fetchall()
    return [_row_to_dossier(r) for r in rows]


def update_dossier(dossier_id: str, patch: m.DossierUpdate) -> Optional[m.Dossier]:
    fields: list[tuple[str, object]] = []
    if patch.title is not None:
        fields.append(("title", patch.title))
    if patch.problem_statement is not None:
        fields.append(("problem_statement", patch.problem_statement))
    if patch.out_of_scope is not None:
        fields.append(("out_of_scope", json.dumps(patch.out_of_scope)))
    if patch.status is not None:
        fields.append(("status", patch.status.value))
    if patch.check_in_policy is not None:
        fields.append(("check_in_policy", patch.check_in_policy.model_dump_json()))
    if not fields:
        return get_dossier(dossier_id)
    fields.append(("updated_at", _dt_str(m.utc_now())))
    set_clause = ", ".join(f"{k} = ?" for k, _ in fields)
    values = [v for _, v in fields] + [dossier_id]
    with connect() as conn:
        conn.execute(f"UPDATE dossiers SET {set_clause} WHERE id = ?", values)
    return get_dossier(dossier_id)


def delete_dossier(dossier_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM dossiers WHERE id = ?", (dossier_id,))
        return cur.rowcount > 0


def get_dossier_resume_state(dossier_id: str) -> Optional[dict]:
    """Compact "can we resume this dossier?" snapshot.

    Read-only. Returns ``None`` if the dossier is missing (so callers can
    map that to a 404). Otherwise returns a dict of the shape documented
    in the Day-3 brief:

        {
          "dossier_id": str,
          "has_plan": bool,
          "plan_approved": bool,
          "active_work_session_id": Optional[str],
          "last_session_ended_at": Optional[datetime],
          "last_visited_at": Optional[datetime],
          "open_needs_input_count": int,
          "open_decision_point_count": int,
          "delivered": bool,  # dossier.status == delivered
        }

    Uses a single connection so the counts are drawn from a consistent
    snapshot of the DB rather than racing mid-turn agent writes.
    """
    with connect() as conn:
        dossier_row = conn.execute(
            "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if dossier_row is None:
            return None

        plan_json = dossier_row["investigation_plan"]
        has_plan = plan_json is not None and plan_json != ""
        plan_approved = False
        if has_plan:
            try:
                plan = m.InvestigationPlan.model_validate_json(plan_json)
                plan_approved = plan.approved_at is not None
            except Exception:
                # Corrupt JSON shouldn't break resume-state — surface as
                # "has plan but not approved" so the user isn't blocked.
                plan_approved = False

        # Active session: ended_at IS NULL. We sort by started_at DESC and
        # take the most recent — in theory there's only one, but if a prior
        # crash left duplicates this picks the latest deterministically.
        active_row = conn.execute(
            "SELECT id FROM work_sessions "
            "WHERE dossier_id = ? AND ended_at IS NULL "
            "ORDER BY started_at DESC LIMIT 1",
            (dossier_id,),
        ).fetchone()
        active_work_session_id = active_row["id"] if active_row else None

        # Last ended session — informs "how long has nothing been
        # happening?" in the UI. NULL if the dossier has never had a
        # session end.
        last_ended_row = conn.execute(
            "SELECT ended_at FROM work_sessions "
            "WHERE dossier_id = ? AND ended_at IS NOT NULL "
            "ORDER BY ended_at DESC LIMIT 1",
            (dossier_id,),
        ).fetchone()
        last_session_ended_at = (
            _dt(last_ended_row["ended_at"]) if last_ended_row else None
        )

        open_ni_row = conn.execute(
            "SELECT COUNT(*) AS n FROM needs_input "
            "WHERE dossier_id = ? AND answered_at IS NULL",
            (dossier_id,),
        ).fetchone()
        open_needs_input_count = int(open_ni_row["n"]) if open_ni_row else 0

        open_dp_row = conn.execute(
            "SELECT COUNT(*) AS n FROM decision_points "
            "WHERE dossier_id = ? AND resolved_at IS NULL",
            (dossier_id,),
        ).fetchone()
        open_decision_point_count = int(open_dp_row["n"]) if open_dp_row else 0

        delivered = dossier_row["status"] == m.DossierStatus.delivered.value

        # Sleep-mode wake state — surfaced so the UI can render a "zzz
        # waking in 2h" indicator or "waking now" badge. These columns
        # may be missing on a very old row; _row_get handles that.
        wake_at_raw = _row_get(dossier_row, "wake_at")
        wake_pending = bool(_row_get(dossier_row, "wake_pending") or 0)
        wake_reason = _row_get(dossier_row, "wake_reason")

        return {
            "dossier_id": dossier_id,
            "has_plan": has_plan,
            "plan_approved": plan_approved,
            "active_work_session_id": active_work_session_id,
            "last_session_ended_at": last_session_ended_at,
            "last_visited_at": _dt(dossier_row["last_visited_at"]),
            "open_needs_input_count": open_needs_input_count,
            "open_decision_point_count": open_decision_point_count,
            "delivered": delivered,
            "wake_at": _dt(wake_at_raw) if wake_at_raw else None,
            "wake_pending": wake_pending,
            "wake_reason": wake_reason,
        }


def mark_dossier_visited(dossier_id: str) -> Optional[m.Dossier]:
    """End any active work_session and update last_visited_at. Called when the user opens the dossier."""
    now = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET ended_at = ? WHERE dossier_id = ? AND ended_at IS NULL",
            (now, dossier_id),
        )
        conn.execute(
            "UPDATE dossiers SET last_visited_at = ?, updated_at = ? WHERE id = ?",
            (now, now, dossier_id),
        )
    return get_dossier(dossier_id)


def get_dossier_full(dossier_id: str) -> Optional[m.DossierFull]:
    dossier = get_dossier(dossier_id)
    if not dossier:
        return None
    return m.DossierFull(
        dossier=dossier,
        sections=list_sections(dossier_id),
        needs_input=list_needs_input(dossier_id),
        decision_points=list_decision_points(dossier_id),
        reasoning_trail=list_reasoning_trail(dossier_id),
        ruled_out=list_ruled_out(dossier_id),
        work_sessions=list_work_sessions(dossier_id),
        next_actions=list_next_actions(dossier_id),
        artifacts=list_artifacts(dossier_id),
        sub_investigations=list_sub_investigations(dossier_id),
        # v2: cap investigation_log at the most recent 500 entries to keep the
        # aggregate payload bounded on hot dossiers.
        investigation_log=list_investigation_log(dossier_id, limit=500),
        considered_and_rejected=list_considered_and_rejected(dossier_id),
        session_summaries=list_session_summaries_for_dossier(dossier_id),
    )


# ---------- Sections ----------


_ORDER_STEP = 10.0


def _compute_order(conn: sqlite3.Connection, dossier_id: str, after_section_id: Optional[str]) -> float:
    """Place section immediately after the given section, or at end if None."""
    rows = conn.execute(
        'SELECT id, "order" FROM sections WHERE dossier_id = ? ORDER BY "order"',
        (dossier_id,),
    ).fetchall()
    if not rows:
        return _ORDER_STEP
    if after_section_id is None:
        return rows[-1]["order"] + _ORDER_STEP
    for i, row in enumerate(rows):
        if row["id"] == after_section_id:
            next_order = rows[i + 1]["order"] if i + 1 < len(rows) else row["order"] + 2 * _ORDER_STEP
            return (row["order"] + next_order) / 2
    # after_section_id not found — fall back to end
    return rows[-1]["order"] + _ORDER_STEP


def list_sections(dossier_id: str) -> list[m.Section]:
    with connect() as conn:
        rows = conn.execute(
            'SELECT * FROM sections WHERE dossier_id = ? ORDER BY "order"',
            (dossier_id,),
        ).fetchall()
    return [_row_to_section(r) for r in rows]


def get_section(section_id: str) -> Optional[m.Section]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    return _row_to_section(row) if row else None


def upsert_section(
    dossier_id: str,
    data: m.SectionUpsert,
    work_session_id: Optional[str] = None,
) -> m.Section:
    now = m.utc_now()
    now_s = _dt_str(now)
    with connect() as conn:
        if data.section_id:
            existing = conn.execute(
                "SELECT * FROM sections WHERE id = ? AND dossier_id = ?",
                (data.section_id, dossier_id),
            ).fetchone()
            if not existing:
                raise KeyError(f"section {data.section_id} not found in dossier {dossier_id}")
            conn.execute(
                """
                UPDATE sections SET type = ?, title = ?, content = ?, state = ?,
                    change_note = ?, sources = ?, depends_on = ?, last_updated = ?
                WHERE id = ?
                """,
                (
                    data.type.value,
                    data.title,
                    data.content,
                    data.state.value,
                    data.change_note,
                    _SourceList.dump_json(data.sources).decode(),
                    json.dumps(data.depends_on),
                    now_s,
                    data.section_id,
                ),
            )
            kind: m.ChangeKind = "section_updated"
            section_id = data.section_id
            if existing["state"] != data.state.value:
                _log_change(conn, dossier_id, work_session_id, "state_changed",
                            f"{data.title}: {existing['state']} → {data.state.value}", section_id)
        else:
            section_id = m.new_id("sec")
            order = _compute_order(conn, dossier_id, data.after_section_id)
            conn.execute(
                """
                INSERT INTO sections (id, dossier_id, type, title, content, state, "order",
                                      change_note, sources, depends_on, last_updated, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    section_id,
                    dossier_id,
                    data.type.value,
                    data.title,
                    data.content,
                    data.state.value,
                    order,
                    data.change_note,
                    _SourceList.dump_json(data.sources).decode(),
                    json.dumps(data.depends_on),
                    now_s,
                    now_s,
                ),
            )
            kind = "section_created"
        _log_change(conn, dossier_id, work_session_id, kind, data.change_note or data.title, section_id)
        _touch_dossier(conn, dossier_id)
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    return _row_to_section(row)


def update_section_state(
    dossier_id: str,
    section_id: str,
    patch: m.SectionStateUpdate,
    work_session_id: Optional[str] = None,
) -> m.Section:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sections WHERE id = ? AND dossier_id = ?",
            (section_id, dossier_id),
        ).fetchone()
        if not existing:
            raise KeyError(f"section {section_id} not found in dossier {dossier_id}")
        conn.execute(
            "UPDATE sections SET state = ?, change_note = ?, last_updated = ? WHERE id = ?",
            (patch.new_state.value, patch.reason, now_s, section_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "state_changed",
            f"{existing['title']}: {existing['state']} → {patch.new_state.value} ({patch.reason})",
            section_id,
        )
        # Mirror into reasoning_trail so cross-session coherence is preserved.
        conn.execute(
            """
            INSERT INTO reasoning_trail (id, dossier_id, work_session_id, note, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                m.new_id("rtr"),
                dossier_id,
                work_session_id,
                f"[state_change] {existing['title']}: {existing['state']} → {patch.new_state.value}. Reason: {patch.reason}",
                json.dumps(["state_change"]),
                now_s,
            ),
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    return _row_to_section(row)


def delete_section(
    dossier_id: str,
    section_id: str,
    reason: str,
    work_session_id: Optional[str] = None,
) -> bool:
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sections WHERE id = ? AND dossier_id = ?",
            (section_id, dossier_id),
        ).fetchone()
        if not existing:
            return False
        conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
        _log_change(
            conn, dossier_id, work_session_id, "section_deleted",
            f"Deleted '{existing['title']}': {reason}", section_id,
        )
        _touch_dossier(conn, dossier_id)
    return True


def reorder_sections(
    dossier_id: str,
    section_ids: list[str],
    work_session_id: Optional[str] = None,
) -> list[m.Section]:
    with connect() as conn:
        existing_ids = {
            r["id"]
            for r in conn.execute(
                "SELECT id FROM sections WHERE dossier_id = ?", (dossier_id,)
            ).fetchall()
        }
        if set(section_ids) != existing_ids:
            raise ValueError("reorder section_ids must match existing section set exactly")
        for i, sid in enumerate(section_ids, start=1):
            conn.execute(
                'UPDATE sections SET "order" = ? WHERE id = ?',
                (i * _ORDER_STEP, sid),
            )
        _log_change(
            conn, dossier_id, work_session_id, "sections_reordered",
            f"Reordered {len(section_ids)} sections",
        )
        _touch_dossier(conn, dossier_id)
    return list_sections(dossier_id)


# ---------- NeedsInput ----------


def add_needs_input(
    dossier_id: str,
    data: m.NeedsInputCreate,
    work_session_id: Optional[str] = None,
) -> m.NeedsInput:
    now = m.utc_now()
    item = m.NeedsInput(
        id=m.new_id("ni"),
        dossier_id=dossier_id,
        question=data.question,
        blocks_section_ids=data.blocks_section_ids,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO needs_input (id, dossier_id, question, blocks_section_ids, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (item.id, dossier_id, item.question, json.dumps(item.blocks_section_ids), _dt_str(now)),
        )
        _log_change(conn, dossier_id, work_session_id, "needs_input_added", item.question)
        _touch_dossier(conn, dossier_id)
    return item


def resolve_needs_input(
    dossier_id: str,
    needs_input_id: str,
    answer: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.NeedsInput]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM needs_input WHERE id = ? AND dossier_id = ?",
            (needs_input_id, dossier_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE needs_input SET answered_at = ?, answer = ? WHERE id = ?",
            (now_s, answer, needs_input_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "needs_input_resolved",
            f"Answered: {row['question']}",
        )
        _touch_dossier(conn, dossier_id)
        # Reactive wake: the scheduler will pick this up on its next tick and
        # resume the agent. Only if sleep mode is on — with it off, the user
        # is driving resumes manually, so we don't want a reactive-start to
        # race the manual POST /resume.
        sleep_mode_on = True
        try:
            setting = conn.execute(
                "SELECT value_json FROM settings WHERE key = 'sleep_mode_enabled'"
            ).fetchone()
            if setting is not None:
                sleep_mode_on = json.loads(setting["value_json"])
        except Exception:
            pass
        if sleep_mode_on:
            conn.execute(
                "UPDATE dossiers SET wake_pending = 1, wake_reason = ? WHERE id = ?",
                (m.WakeReason.needs_input_resolved.value, dossier_id),
            )
        row = conn.execute("SELECT * FROM needs_input WHERE id = ?", (needs_input_id,)).fetchone()
    return _row_to_needs_input(row)


def list_needs_input(dossier_id: str, open_only: bool = False) -> list[m.NeedsInput]:
    q = "SELECT * FROM needs_input WHERE dossier_id = ?"
    if open_only:
        q += " AND answered_at IS NULL"
    q += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(q, (dossier_id,)).fetchall()
    return [_row_to_needs_input(r) for r in rows]


# ---------- DecisionPoint ----------


def add_decision_point(
    dossier_id: str,
    data: m.DecisionPointCreate,
    work_session_id: Optional[str] = None,
) -> m.DecisionPoint:
    now = m.utc_now()
    item = m.DecisionPoint(
        id=m.new_id("dp"),
        dossier_id=dossier_id,
        title=data.title,
        options=data.options,
        recommendation=data.recommendation,
        blocks_section_ids=data.blocks_section_ids,
        kind=data.kind,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO decision_points (id, dossier_id, title, options, recommendation,
                                         blocks_section_ids, kind, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                dossier_id,
                item.title,
                _OptionList.dump_json(item.options).decode(),
                item.recommendation,
                json.dumps(item.blocks_section_ids),
                item.kind,
                _dt_str(now),
            ),
        )
        _log_change(conn, dossier_id, work_session_id, "decision_point_added", item.title)
        _touch_dossier(conn, dossier_id)
    return item


_APPROVE_PATTERN = __import__("re").compile(r"approve|approved|yes", __import__("re").IGNORECASE)


def resolve_decision_point(
    dossier_id: str,
    decision_id: str,
    chosen: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.DecisionPoint]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM decision_points WHERE id = ? AND dossier_id = ?",
            (decision_id, dossier_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE decision_points SET resolved_at = ?, chosen = ? WHERE id = ?",
            (now_s, chosen, decision_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "decision_point_resolved",
            f"Decided '{row['title']}' → {chosen}",
        )
        _touch_dossier(conn, dossier_id)
        # Reactive wake: same contract as resolve_needs_input — when the user
        # decides, the scheduler picks it up on the next tick and resumes the
        # agent. Without this hook, a plan_approval sits forever after the
        # user clicks Approve. Sleep-mode-gated so a disabled-mode user still
        # drives resumes manually.
        sleep_mode_on = True
        try:
            setting = conn.execute(
                "SELECT value_json FROM settings WHERE key = 'sleep_mode_enabled'"
            ).fetchone()
            if setting is not None:
                sleep_mode_on = json.loads(setting["value_json"])
        except Exception:
            pass
        if sleep_mode_on:
            conn.execute(
                "UPDATE dossiers SET wake_pending = 1, wake_reason = ? WHERE id = ?",
                (m.WakeReason.decision_resolved.value, dossier_id),
            )
        row = conn.execute("SELECT * FROM decision_points WHERE id = ?", (decision_id,)).fetchone()
    resolved = _row_to_decision_point(row)
    # Auto-approve plan if this is a plan_approval decision with an approving choice.
    if resolved.kind == "plan_approval" and _APPROVE_PATTERN.search(chosen or ""):
        approve_investigation_plan(dossier_id, work_session_id)
    return resolved


def list_decision_points(dossier_id: str, open_only: bool = False) -> list[m.DecisionPoint]:
    q = "SELECT * FROM decision_points WHERE dossier_id = ?"
    if open_only:
        q += " AND resolved_at IS NULL"
    q += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(q, (dossier_id,)).fetchall()
    return [_row_to_decision_point(r) for r in rows]


# ---------- ReasoningTrail ----------


def append_reasoning(
    dossier_id: str,
    data: m.ReasoningAppend,
    work_session_id: Optional[str] = None,
) -> m.ReasoningTrailEntry:
    now = m.utc_now()
    entry = m.ReasoningTrailEntry(
        id=m.new_id("rtr"),
        dossier_id=dossier_id,
        work_session_id=work_session_id,
        note=data.note,
        tags=data.tags,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO reasoning_trail (id, dossier_id, work_session_id, note, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                dossier_id,
                work_session_id,
                entry.note,
                json.dumps(entry.tags),
                _dt_str(now),
            ),
        )
    return entry


def list_reasoning_trail(dossier_id: str) -> list[m.ReasoningTrailEntry]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reasoning_trail WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_reasoning(r) for r in rows]


# ---------- RuledOut ----------


def add_ruled_out(
    dossier_id: str,
    data: m.RuledOutCreate,
    work_session_id: Optional[str] = None,
) -> m.RuledOut:
    now = m.utc_now()
    item = m.RuledOut(
        id=m.new_id("ro"),
        dossier_id=dossier_id,
        subject=data.subject,
        reason=data.reason,
        sources=data.sources,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO ruled_out (id, dossier_id, subject, reason, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                dossier_id,
                item.subject,
                item.reason,
                _SourceList.dump_json(item.sources).decode(),
                _dt_str(now),
            ),
        )
        _log_change(conn, dossier_id, work_session_id, "ruled_out_added", f"Ruled out: {item.subject}")
        _touch_dossier(conn, dossier_id)
    return item


def list_ruled_out(dossier_id: str) -> list[m.RuledOut]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ruled_out WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_ruled_out(r) for r in rows]


# ---------- WorkSession ----------


def start_work_session(
    dossier_id: str,
    trigger: m.WorkSessionTrigger = m.WorkSessionTrigger.manual,
) -> m.WorkSession:
    now = m.utc_now()
    session = m.WorkSession(
        id=m.new_id("ws"),
        dossier_id=dossier_id,
        started_at=now,
        trigger=trigger,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO work_sessions (id, dossier_id, started_at, trigger, token_budget_used)
            VALUES (?, ?, ?, ?, 0)
            """,
            (session.id, dossier_id, _dt_str(now), trigger.value),
        )
    return session


def get_work_session(session_id: str) -> Optional[m.WorkSession]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return _row_to_work_session(row) if row else None


def end_work_session(session_id: str) -> Optional[m.WorkSession]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
            (now_s, session_id),
        )
        row = conn.execute("SELECT * FROM work_sessions WHERE id = ?", (session_id,)).fetchone()
    return _row_to_work_session(row) if row else None


def get_active_work_session(dossier_id: str) -> Optional[m.WorkSession]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE dossier_id = ? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (dossier_id,),
        ).fetchone()
    return _row_to_work_session(row) if row else None


def list_work_sessions(dossier_id: str) -> list[m.WorkSession]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM work_sessions WHERE dossier_id = ? ORDER BY started_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_work_session(r) for r in rows]


def increment_session_tokens(session_id: str, tokens: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET token_budget_used = token_budget_used + ? WHERE id = ?",
            (tokens, session_id),
        )


def record_session_usage(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """Accumulate per-turn usage on a work_session row.

    Called once per model turn in the runtime. Rolls up tokens and dollar
    cost; used by the budget-tracking surface and by the per-session UI
    header. Also bumps the aggregate token_budget_used counter so existing
    readers don't regress.
    """
    with connect() as conn:
        conn.execute(
            """
            UPDATE work_sessions
               SET input_tokens = input_tokens + ?,
                   output_tokens = output_tokens + ?,
                   cost_usd = cost_usd + ?,
                   token_budget_used = token_budget_used + ?
             WHERE id = ?
            """,
            (
                int(input_tokens),
                int(output_tokens),
                float(cost_usd),
                int(input_tokens + output_tokens),
                session_id,
            ),
        )


def end_work_session_with_reason(
    session_id: str,
    reason: m.WorkSessionEndReason,
) -> Optional[m.WorkSession]:
    """Close a session and stamp end_reason atomically.

    Preferred over end_work_session() for new call sites. end_work_session
    stays for the legacy path (lifecycle reconcile, etc.), which stamps the
    crashed reason via a separate helper below.
    """
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            """
            UPDATE work_sessions
               SET ended_at = ?,
                   end_reason = ?
             WHERE id = ? AND ended_at IS NULL
            """,
            (now_s, reason.value, session_id),
        )
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return _row_to_work_session(row) if row else None


def end_orphan_session_as_crashed(session_id: str) -> Optional[m.WorkSession]:
    """Used by lifecycle reconcile to close a process-crash leftover."""
    return end_work_session_with_reason(session_id, m.WorkSessionEndReason.crashed)


# ---------- v2: InvestigationLog ----------
#
# Typed, append-only "evidence of work" and stuck-signal surface. Separate from
# change_log (user-visit-diff) by design — appends here do NOT write to
# change_log, so the "47 sources consulted" counter doesn't pollute the
# since-last-visit plan-diff the user reads on return.


def _row_to_investigation_log(row: sqlite3.Row) -> m.InvestigationLogEntry:
    return m.InvestigationLogEntry(
        id=row["id"],
        dossier_id=row["dossier_id"],
        work_session_id=row["work_session_id"],
        sub_investigation_id=row["sub_investigation_id"],
        entry_type=m.InvestigationLogEntryType(row["entry_type"]),
        payload=json.loads(row["payload"]) if row["payload"] else {},
        summary=row["summary"],
        created_at=_dt(row["created_at"]),
    )


# ---------- ChangeLog ----------


def list_change_log_for_session(dossier_id: str, session_id: str) -> list[m.ChangeLogEntry]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM change_log WHERE dossier_id = ? AND work_session_id = ? ORDER BY created_at",
            (dossier_id, session_id),
        ).fetchall()
    return [_row_to_change(r) for r in rows]


# ---------- Debrief ----------


def update_debrief(
    dossier_id: str,
    patch: m.DebriefUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Merge non-None fields into existing debrief, set last_updated, persist, log, touch."""
    with connect() as conn:
        row = conn.execute(
            "SELECT debrief FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        existing_json = row["debrief"]
        if existing_json:
            current = m.Debrief.model_validate_json(existing_json)
        else:
            current = m.Debrief(last_updated=m.utc_now())
        # Sanitize incoming fields: strip any XML-style tool-call markup
        # the model fell back to emitting (`<parameter name="...">`,
        # `</invoke>`, `</what_i_did>`, etc.).
        sanitized_patch = {
            k: (_strip_tool_markup(v) if isinstance(v, str) else v)
            for k, v in patch.model_dump(exclude_none=True).items()
        }
        merged = current.model_copy(update=sanitized_patch)
        merged = merged.model_copy(update={"last_updated": m.utc_now()})
        conn.execute(
            "UPDATE dossiers SET debrief = ? WHERE id = ?",
            (merged.model_dump_json(), dossier_id),
        )
        note_parts = [k for k, v in patch.model_dump(exclude_none=True).items()]
        note = "Debrief updated: " + (", ".join(note_parts) if note_parts else "(no changes)")
        _log_change(conn, dossier_id, work_session_id, "debrief_updated", note)
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


# ---------- WorkingTheory (phase 2) ----------


def update_working_theory(
    dossier_id: str,
    patch: m.WorkingTheoryUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Partial-merge update with a required-fields gate on first write.

    - If no prior theory exists on the dossier, patch MUST supply all four
      fields (recommendation, confidence, why, what_would_change_it) —
      there's no meaningful state to merge onto. We raise ValueError with a
      list of missing fields so the tool layer can surface a clear message.
    - If a prior theory exists, any field omitted retains its prior value.
    - updated_at is always refreshed.
    - Emits a ``working_theory_updated`` change_log entry. When
      ``confidence`` changes specifically, an additional ``state_changed``
      entry is also emitted so the plan-diff shows the transition prominently.
    """
    now = m.utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT working_theory FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        existing_raw = _row_get(row, "working_theory")
        current: Optional[m.WorkingTheory] = (
            m.WorkingTheory.model_validate_json(existing_raw)
            if existing_raw else None
        )
        patch_data = patch.model_dump(exclude_none=True)
        # Strip XML-style tool-call markup from prose fields before merge.
        for _k in ("recommendation", "why", "what_would_change_it"):
            if _k in patch_data and isinstance(patch_data[_k], str):
                patch_data[_k] = _strip_tool_markup(patch_data[_k]) or ""
        if "unresolved_assumptions" in patch_data:
            patch_data["unresolved_assumptions"] = _strip_tool_markup_list(
                patch_data["unresolved_assumptions"]
            )
        if current is None:
            required = {"recommendation", "confidence", "why", "what_would_change_it"}
            missing = sorted(required - set(patch_data.keys()))
            if missing:
                raise ValueError(
                    "update_working_theory: first write must include all fields; "
                    f"missing: {', '.join(missing)}"
                )
            merged = m.WorkingTheory(
                recommendation=patch_data["recommendation"],
                confidence=m.WorkingTheoryConfidence(patch_data["confidence"])
                    if not isinstance(patch_data["confidence"], m.WorkingTheoryConfidence)
                    else patch_data["confidence"],
                why=patch_data["why"],
                what_would_change_it=patch_data["what_would_change_it"],
                unresolved_assumptions=patch_data.get("unresolved_assumptions", []),
                updated_at=now,
            )
            old_confidence = None
        else:
            merged = current.model_copy(update={**patch_data, "updated_at": now})
            old_confidence = current.confidence

        conn.execute(
            "UPDATE dossiers SET working_theory = ? WHERE id = ?",
            (merged.model_dump_json(), dossier_id),
        )

        confidence_changed = (
            old_confidence is not None and old_confidence != merged.confidence
        )
        changed_fields = list(patch_data.keys())
        note_body = (
            ", ".join(changed_fields) if changed_fields else "(no changes)"
        )
        if current is None:
            note = (
                f"Working theory drafted ({merged.confidence.value}): "
                f"{merged.recommendation[:120]}"
            )
        else:
            note = (
                f"Working theory updated ({merged.confidence.value}): "
                f"{note_body}"
            )
        _log_change(
            conn, dossier_id, work_session_id, "working_theory_updated", note,
        )
        if confidence_changed:
            _log_change(
                conn, dossier_id, work_session_id, "state_changed",
                f"working_theory: {old_confidence.value} → {merged.confidence.value}",
            )
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


# ---------- PremiseChallenge (phase 4) ----------


def update_premise_challenge(
    dossier_id: str,
    patch: m.PremiseChallengeUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Partial-merge update. First write requires all five content fields.

    Emits a `debrief_updated` change_log entry (re-using the existing Plan
    & debrief category in the plan-diff) with a terse note. We deliberately
    do NOT add a new ChangeKind for premise-challenge updates — the
    frontend already categorizes `debrief_updated` under plan & debrief,
    which is the right bucket for this surface.
    """
    now = m.utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT premise_challenge FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        existing_raw = _row_get(row, "premise_challenge")
        current: Optional[m.PremiseChallenge] = (
            m.PremiseChallenge.model_validate_json(existing_raw)
            if existing_raw else None
        )
        patch_data = patch.model_dump(exclude_none=True)
        # Strip XML-style tool-call markup the model sometimes emits.
        for _k in ("original_question", "why_answering_now_is_risky", "safer_reframe"):
            if _k in patch_data and isinstance(patch_data[_k], str):
                patch_data[_k] = _strip_tool_markup(patch_data[_k]) or ""
        for _k in ("hidden_assumptions", "required_evidence_before_answering"):
            if _k in patch_data:
                patch_data[_k] = _strip_tool_markup_list(patch_data[_k])
        if current is None:
            required = {
                "original_question", "hidden_assumptions",
                "why_answering_now_is_risky", "safer_reframe",
                "required_evidence_before_answering",
            }
            missing = sorted(required - set(patch_data.keys()))
            if missing:
                raise ValueError(
                    "update_premise_challenge: first write must include all "
                    f"fields; missing: {', '.join(missing)}"
                )
            merged = m.PremiseChallenge(
                original_question=patch_data["original_question"],
                hidden_assumptions=patch_data["hidden_assumptions"],
                why_answering_now_is_risky=patch_data["why_answering_now_is_risky"],
                safer_reframe=patch_data["safer_reframe"],
                required_evidence_before_answering=patch_data["required_evidence_before_answering"],
                updated_at=now,
            )
        else:
            merged = current.model_copy(update={**patch_data, "updated_at": now})

        conn.execute(
            "UPDATE dossiers SET premise_challenge = ? WHERE id = ?",
            (merged.model_dump_json(), dossier_id),
        )
        changed_fields = list(patch_data.keys())
        note_body = ", ".join(changed_fields) if changed_fields else "(no changes)"
        note = (
            f"Premise challenge drafted: {merged.safer_reframe[:120]}"
            if current is None
            else f"Premise challenge updated: {note_body}"
        )
        _log_change(
            conn, dossier_id, work_session_id, "debrief_updated", note,
        )
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


# ---------- InvestigationPlan ----------


def update_investigation_plan(
    dossier_id: str,
    data: m.InvestigationPlanUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Replace items + rationale. Sets revised_at + increments revision_count if
    plan exists; sets drafted_at if new. Sets approved_at to now if approve=True
    and approved_at is None. Logs ``plan_updated``."""
    now = m.utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT investigation_plan FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        existing_json = row["investigation_plan"]
        if existing_json:
            current = m.InvestigationPlan.model_validate_json(existing_json)
            new_plan = m.InvestigationPlan(
                items=data.items,
                rationale=data.rationale,
                drafted_at=current.drafted_at,
                approved_at=current.approved_at,
                revised_at=now,
                revision_count=current.revision_count + 1,
            )
        else:
            new_plan = m.InvestigationPlan(
                items=data.items,
                rationale=data.rationale,
                drafted_at=now,
                approved_at=None,
                revised_at=None,
                revision_count=0,
            )
        if data.approve and new_plan.approved_at is None:
            new_plan = new_plan.model_copy(update={"approved_at": now})
        conn.execute(
            "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
            (new_plan.model_dump_json(), dossier_id),
        )
        if existing_json:
            note = f"Plan revised (rev {new_plan.revision_count}, {len(new_plan.items)} items)"
        else:
            note = f"Plan drafted ({len(new_plan.items)} items)"
        if data.approve:
            note += " — approved"
        _log_change(conn, dossier_id, work_session_id, "plan_updated", note)
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


def replan_dossier(dossier_id: str) -> dict:
    """Backfill or reset the plan_approval decision_point for a dossier.

    One endpoint, three behaviours depending on current state:

    - **No investigation_plan drafted** → returns
      ``{"ok": False, "reason": "no_plan"}``. The agent drafts the plan on
      first turn; nothing to approve-or-redirect yet.
    - **Plan drafted, no open plan_approval decision_point** (backfill case:
      legacy dossiers predating the intake-time plan_approval creation, or
      dossiers whose prior approval was generated but then the DP was
      resolved with Redirect without generating a new one) → creates a
      fresh plan_approval DP. Returns ``{"ok": True, "action": "backfilled",
      ...}``.
    - **Plan drafted, plan_approval DP already open** → idempotent; returns
      ``{"ok": True, "action": "already_pending", "decision_point_id": ...}``
      without creating a duplicate.
    - **Plan already approved** → un-approves the plan AND creates a fresh
      plan_approval DP. Returns ``{"ok": True, "action": "replanned",
      "plan_unapproved": True, ...}``. The next ``resolve_decision_point``
      on this new DP will re-approve via the existing auto-approve path.

    Does NOT set wake_pending. The existing ``resolve_decision_point`` hook
    handles waking the agent when the user actually resolves the new DP.
    """
    dossier = get_dossier(dossier_id)
    if dossier is None:
        return {"ok": False, "reason": "not_found"}
    plan = dossier.investigation_plan
    if plan is None:
        return {"ok": False, "reason": "no_plan"}

    # Short-circuit: already an open plan_approval DP and plan is unapproved.
    existing_open = [
        dp for dp in list_decision_points(dossier_id, open_only=True)
        if dp.kind == "plan_approval"
    ]
    plan_unapproved = False
    if plan.approved_at is not None:
        # Replan: unapprove the plan so the UI hides the "approved" banner
        # and the agent sees plan as a gate again on its next turn.
        now = m.utc_now()
        unapproved = plan.model_copy(update={
            "approved_at": None,
            "revised_at": now,
            "revision_count": plan.revision_count + 1,
        })
        with connect() as conn:
            conn.execute(
                "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
                (unapproved.model_dump_json(), dossier_id),
            )
            _log_change(
                conn, dossier_id, None, "plan_updated",
                "Plan un-approved (replan requested); awaiting fresh approval.",
            )
            _touch_dossier(conn, dossier_id)
        plan_unapproved = True
    elif existing_open:
        # Idempotent: return the one that's already open.
        return {
            "ok": True,
            "action": "already_pending",
            "dossier_id": dossier_id,
            "decision_point_id": existing_open[0].id,
            "plan_unapproved": False,
        }

    # Create the fresh plan_approval DP. Shape mirrors the intake-time
    # creation in vellum.intake.tools.commit_intake so the user sees the
    # same options regardless of how the DP was generated.
    action = "replanned" if plan_unapproved else "backfilled"
    dp = add_decision_point(
        dossier_id,
        m.DecisionPointCreate(
            title="Approve investigation plan, or redirect?",
            options=[
                m.DecisionOption(
                    label="Approve",
                    implications=(
                        "Approve the plan as drafted. The agent will start "
                        "substantive investigation on its next wake."
                    ),
                    recommended=True,
                ),
                m.DecisionOption(
                    label="Redirect",
                    implications=(
                        "Ask the agent to reframe before starting — useful if "
                        "the plan is missing a key angle or assumes the wrong "
                        "framing. The agent will re-draft the plan and surface "
                        "a fresh approval."
                    ),
                    recommended=False,
                ),
            ],
            recommendation=(
                "Review the plan items above. Approve to unblock substantive "
                "work, or redirect if the framing is off."
            ),
            kind="plan_approval",
        ),
        work_session_id=None,
    )
    return {
        "ok": True,
        "action": action,
        "dossier_id": dossier_id,
        "decision_point_id": dp.id,
        "plan_unapproved": plan_unapproved,
    }


def approve_investigation_plan(
    dossier_id: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Stamp approved_at = now on the dossier's plan. No-op if plan is null or
    already approved. Logs a plan_updated change_log entry on first approval."""
    now = m.utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT investigation_plan FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        plan_json = row["investigation_plan"]
        if not plan_json:
            return get_dossier(dossier_id)
        current = m.InvestigationPlan.model_validate_json(plan_json)
        if current.approved_at is not None:
            return get_dossier(dossier_id)
        approved = current.model_copy(update={"approved_at": now})
        conn.execute(
            "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
            (approved.model_dump_json(), dossier_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "plan_updated",
            f"Plan approved ({len(approved.items)} items)",
        )
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


# ---------- NextAction ----------


def _compute_next_action_priority(
    conn: sqlite3.Connection, dossier_id: str, after_action_id: Optional[str]
) -> float:
    """Place the new action right after ``after_action_id``, or at the end if None.
    Mirrors _compute_order for sections."""
    rows = conn.execute(
        "SELECT id, priority FROM next_actions WHERE dossier_id = ? ORDER BY priority",
        (dossier_id,),
    ).fetchall()
    if not rows:
        return _ORDER_STEP
    if after_action_id is None:
        return rows[-1]["priority"] + _ORDER_STEP
    for i, row in enumerate(rows):
        if row["id"] == after_action_id:
            next_p = (
                rows[i + 1]["priority"]
                if i + 1 < len(rows)
                else row["priority"] + 2 * _ORDER_STEP
            )
            return (row["priority"] + next_p) / 2
    # after_action_id not found — fall back to end
    return rows[-1]["priority"] + _ORDER_STEP


def add_next_action(
    dossier_id: str,
    data: m.NextActionCreate,
    work_session_id: Optional[str] = None,
) -> m.NextAction:
    now = m.utc_now()
    action_id = m.new_id("act")
    with connect() as conn:
        priority = _compute_next_action_priority(conn, dossier_id, data.after_action_id)
        conn.execute(
            """
            INSERT INTO next_actions (id, dossier_id, action, rationale, priority,
                                      completed, completed_at, created_at)
            VALUES (?, ?, ?, ?, ?, 0, NULL, ?)
            """,
            (
                action_id,
                dossier_id,
                data.action,
                data.rationale,
                priority,
                _dt_str(now),
            ),
        )
        _log_change(
            conn, dossier_id, work_session_id, "next_action_added",
            f"Next action: {data.action}",
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM next_actions WHERE id = ?", (action_id,)
        ).fetchone()
    return _row_to_next_action(row)


def list_next_actions(
    dossier_id: str, include_completed: bool = True
) -> list[m.NextAction]:
    q = "SELECT * FROM next_actions WHERE dossier_id = ?"
    if not include_completed:
        q += " AND completed = 0"
    q += " ORDER BY priority"
    with connect() as conn:
        rows = conn.execute(q, (dossier_id,)).fetchall()
    return [_row_to_next_action(r) for r in rows]


def complete_next_action(
    dossier_id: str,
    action_id: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.NextAction]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM next_actions WHERE id = ? AND dossier_id = ?",
            (action_id, dossier_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE next_actions SET completed = 1, completed_at = ? WHERE id = ?",
            (now_s, action_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "next_action_completed",
            f"Completed: {row['action']}",
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM next_actions WHERE id = ?", (action_id,)
        ).fetchone()
    return _row_to_next_action(row)


def remove_next_action(
    dossier_id: str,
    action_id: str,
    work_session_id: Optional[str] = None,
) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM next_actions WHERE id = ? AND dossier_id = ?",
            (action_id, dossier_id),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM next_actions WHERE id = ?", (action_id,))
        _log_change(
            conn, dossier_id, work_session_id, "next_action_removed",
            f"Removed: {row['action']}",
        )
        _touch_dossier(conn, dossier_id)
    return True


def reorder_next_actions(
    dossier_id: str,
    action_ids: list[str],
    work_session_id: Optional[str] = None,
) -> list[m.NextAction]:
    with connect() as conn:
        existing_ids = {
            r["id"]
            for r in conn.execute(
                "SELECT id FROM next_actions WHERE dossier_id = ?", (dossier_id,)
            ).fetchall()
        }
        if set(action_ids) != existing_ids:
            raise ValueError(
                "reorder action_ids must match existing next_action set exactly"
            )
        for i, aid in enumerate(action_ids, start=1):
            conn.execute(
                "UPDATE next_actions SET priority = ? WHERE id = ?",
                (i * _ORDER_STEP, aid),
            )
        _touch_dossier(conn, dossier_id)
    return list_next_actions(dossier_id)


# ---------- ChangeLog ----------


def list_change_log_since_last_visit(dossier_id: str) -> list[m.ChangeLogEntry]:
    """The plan-diff: everything the agent did since the user was last here."""
    dossier = get_dossier(dossier_id)
    if not dossier:
        return []
    with connect() as conn:
        if dossier.last_visited_at is None:
            rows = conn.execute(
                "SELECT * FROM change_log WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM change_log WHERE dossier_id = ? AND created_at > ? ORDER BY created_at",
                (dossier_id, _dt_str(dossier.last_visited_at)),
            ).fetchall()
    return [_row_to_change(r) for r in rows]


# ---------- Artifacts ----------


def _row_to_artifact(row: sqlite3.Row) -> m.Artifact:
    return m.Artifact(
        id=row["id"],
        dossier_id=row["dossier_id"],
        kind=m.ArtifactKind(row["kind"]),
        title=row["title"],
        content=row["content"],
        intended_use=row["intended_use"],
        state=m.ArtifactState(row["state"]),
        kind_note=row["kind_note"],
        supersedes=row["supersedes"],
        last_updated=_dt(row["last_updated"]),
        created_at=_dt(row["created_at"]),
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
            conn, dossier_id, work_session_id, "artifact_updated",
            f"Deleted artifact: {existing['title']}",
        )
        _touch_dossier(conn, dossier_id)
    return True


# ---------- SubInvestigations ----------


def _row_to_sub_investigation(row: sqlite3.Row) -> m.SubInvestigation:
    return m.SubInvestigation(
        id=row["id"],
        dossier_id=row["dossier_id"],
        parent_section_id=row["parent_section_id"],
        plan_item_id=_row_get(row, "plan_item_id"),
        title=_row_get(row, "title"),
        scope=row["scope"],
        questions=_json_list(row["questions"]),
        state=m.SubInvestigationState(row["state"]),
        return_summary=row["return_summary"],
        findings_section_ids=_json_list(row["findings_section_ids"]),
        findings_artifact_ids=_json_list(row["findings_artifact_ids"]),
        why_it_matters=_row_get(row, "why_it_matters"),
        known_facts=_json_list(_row_get(row, "known_facts") or "[]"),
        missing_facts=_json_list(_row_get(row, "missing_facts") or "[]"),
        current_finding=_row_get(row, "current_finding"),
        recommended_next_step=_row_get(row, "recommended_next_step"),
        confidence=m.InvestigationConfidence(_row_get(row, "confidence") or "unknown"),
        blocked_reason=_row_get(row, "blocked_reason"),
        started_at=_dt(row["started_at"]),
        completed_at=_dt(row["completed_at"]),
    )


def _set_plan_item_status(
    conn: sqlite3.Connection,
    dossier_id: str,
    plan_item_id: Optional[str],
    new_status: str,
) -> None:
    """Flip a single plan item's status in the investigation_plan JSON blob.

    No-op when plan_item_id is None, the dossier's plan is missing, the
    item id isn't found in the plan, or the item is already at new_status.
    Writes through Pydantic (model_copy) so extra validation still runs.
    Caller already emits change_log for the owning action
    (sub_investigation_spawned / _completed / _abandoned); we don't add a
    separate plan_updated entry — that would be noise.
    """
    if not plan_item_id:
        return
    row = conn.execute(
        "SELECT investigation_plan FROM dossiers WHERE id = ?", (dossier_id,)
    ).fetchone()
    if not row or not row["investigation_plan"]:
        return
    plan = m.InvestigationPlan.model_validate_json(row["investigation_plan"])
    new_items: list[m.InvestigationPlanItem] = []
    changed = False
    for item in plan.items:
        if item.id == plan_item_id and item.status != new_status:
            new_items.append(item.model_copy(update={"status": new_status}))
            changed = True
        else:
            new_items.append(item)
    if not changed:
        return
    new_plan = plan.model_copy(update={"items": new_items})
    conn.execute(
        "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
        (new_plan.model_dump_json(), dossier_id),
    )


def spawn_sub_investigation(
    dossier_id: str,
    data: m.SubInvestigationSpawn,
    work_session_id: Optional[str] = None,
) -> m.SubInvestigation:
    now = m.utc_now()
    sub = m.SubInvestigation(
        id=m.new_id("sub"),
        dossier_id=dossier_id,
        parent_section_id=data.parent_section_id,
        plan_item_id=data.plan_item_id,
        title=data.title,
        scope=data.scope,
        questions=data.questions,
        state=m.SubInvestigationState.running,
        why_it_matters=data.why_it_matters,
        known_facts=data.known_facts,
        missing_facts=data.missing_facts,
        started_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sub_investigations (id, dossier_id, parent_section_id, plan_item_id,
                                            title, scope, questions, state, return_summary,
                                            findings_section_ids, findings_artifact_ids,
                                            why_it_matters, known_facts, missing_facts,
                                            started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sub.id,
                dossier_id,
                sub.parent_section_id,
                sub.plan_item_id,
                sub.title,
                sub.scope,
                json.dumps(sub.questions),
                sub.state.value,
                sub.return_summary,
                json.dumps(sub.findings_section_ids),
                json.dumps(sub.findings_artifact_ids),
                sub.why_it_matters,
                json.dumps(sub.known_facts),
                json.dumps(sub.missing_facts),
                _dt_str(sub.started_at),
                None,
            ),
        )
        # Sync plan-item status: planned → in_progress when the agent spawns
        # from a plan entry.
        _set_plan_item_status(conn, dossier_id, sub.plan_item_id, "in_progress")
        # Change-log note prefers title when present; scope is the fallback
        # so the plan-diff reads naturally ("Spawned sub-investigation:
        # Verify debt ownership" vs. the longer scope sentence).
        display = sub.title or sub.scope
        _log_change(
            conn, dossier_id, work_session_id, "sub_investigation_spawned",
            f"Spawned sub-investigation: {display}",
        )
        _touch_dossier(conn, dossier_id)
    return sub


def get_sub_investigation(sub_id: str) -> Optional[m.SubInvestigation]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row) if row else None


def list_sub_investigations(
    dossier_id: str,
    state: Optional[m.SubInvestigationState] = None,
) -> list[m.SubInvestigation]:
    q = "SELECT * FROM sub_investigations WHERE dossier_id = ?"
    params: list[object] = [dossier_id]
    if state is not None:
        q += " AND state = ?"
        params.append(state.value)
    q += " ORDER BY started_at"
    with connect() as conn:
        rows = conn.execute(q, params).fetchall()
    return [_row_to_sub_investigation(r) for r in rows]


def update_sub_investigation_state(
    dossier_id: str,
    sub_id: str,
    patch: m.SubInvestigationStateUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.SubInvestigation]:
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ? AND dossier_id = ?",
            (sub_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        # When flipping to blocked, persist the reason; when leaving blocked,
        # clear the field. Both paths go through the same UPDATE so state and
        # reason stay consistent.
        if patch.new_state == m.SubInvestigationState.blocked:
            conn.execute(
                "UPDATE sub_investigations SET state = ?, blocked_reason = ? WHERE id = ?",
                (patch.new_state.value, patch.reason, sub_id),
            )
        else:
            conn.execute(
                "UPDATE sub_investigations SET state = ?, blocked_reason = NULL WHERE id = ?",
                (patch.new_state.value, sub_id),
            )
        display = _row_get(existing, "title") or existing["scope"]
        _log_change(
            conn, dossier_id, work_session_id, "state_changed",
            f"sub-investigation '{display}': "
            f"{existing['state']} → {patch.new_state.value} ({patch.reason})",
        )
        # Sync plan-item status on terminal transitions. Blocked is
        # recoverable — the item stays in_progress so the user sees the
        # thread is still open. Abandoned and delivered are terminal and
        # propagate to the plan item.
        if patch.new_state == m.SubInvestigationState.abandoned:
            _set_plan_item_status(
                conn, dossier_id, _row_get(existing, "plan_item_id"), "abandoned",
            )
        elif patch.new_state == m.SubInvestigationState.delivered:
            _set_plan_item_status(
                conn, dossier_id, _row_get(existing, "plan_item_id"), "completed",
            )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row)


def update_sub_investigation(
    dossier_id: str,
    sub_id: str,
    patch: m.SubInvestigationUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.SubInvestigation]:
    """Partial-merge update of a sub-investigation's semantic fields.

    Updates why_it_matters / known_facts / missing_facts / current_finding /
    recommended_next_step / confidence. Fields omitted retain prior value.
    Emits a `state_changed` change_log entry only when confidence actually
    changes — the label-prefix format ("sub-investigation 'title': old ->
    new") is the one the frontend parser already handles. Text-only updates
    skip change_log (still flow through _touch_dossier so updated_at advances);
    the session_summary tool is the user's surface for text-only progress.
    """
    patch_data = patch.model_dump(exclude_none=True)
    if not patch_data:
        return get_sub_investigation(sub_id)
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ? AND dossier_id = ?",
            (sub_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        # Build dynamic SET clause from whichever fields are in patch_data.
        set_parts: list[str] = []
        values: list[object] = []
        for k, v in patch_data.items():
            if k in ("known_facts", "missing_facts"):
                set_parts.append(f"{k} = ?")
                values.append(json.dumps(v))
            elif k == "confidence":
                set_parts.append(f"{k} = ?")
                values.append(v.value if hasattr(v, "value") else str(v))
            else:
                set_parts.append(f"{k} = ?")
                values.append(v)
        values.append(sub_id)
        conn.execute(
            f"UPDATE sub_investigations SET {', '.join(set_parts)} WHERE id = ?",
            values,
        )
        # Confidence drift: emit state_changed change_log with label prefix
        # the frontend parser knows how to render.
        if "confidence" in patch_data:
            old_conf = _row_get(existing, "confidence") or "unknown"
            new_conf_raw = patch_data["confidence"]
            new_conf = new_conf_raw.value if hasattr(new_conf_raw, "value") else str(new_conf_raw)
            if old_conf != new_conf:
                display = _row_get(existing, "title") or existing["scope"]
                _log_change(
                    conn, dossier_id, work_session_id, "state_changed",
                    f"sub-investigation '{display[:40]}': {old_conf} -> {new_conf}",
                )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row)


def complete_sub_investigation(
    dossier_id: str,
    sub_id: str,
    data: m.SubInvestigationComplete,
    work_session_id: Optional[str] = None,
) -> Optional[m.SubInvestigation]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ? AND dossier_id = ?",
            (sub_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        conn.execute(
            """
            UPDATE sub_investigations
            SET state = ?, return_summary = ?, findings_section_ids = ?,
                findings_artifact_ids = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                m.SubInvestigationState.delivered.value,
                data.return_summary,
                json.dumps(data.findings_section_ids),
                json.dumps(data.findings_artifact_ids),
                now_s,
                sub_id,
            ),
        )
        _log_change(
            conn, dossier_id, work_session_id, "sub_investigation_completed",
            f"Completed sub-investigation '{existing['scope']}': {data.return_summary}",
        )
        # Sync plan-item status: in_progress → completed.
        _set_plan_item_status(
            conn, dossier_id, _row_get(existing, "plan_item_id"), "completed",
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row)


def abandon_sub_investigation(
    dossier_id: str,
    sub_id: str,
    reason: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.SubInvestigation]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ? AND dossier_id = ?",
            (sub_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        conn.execute(
            "UPDATE sub_investigations SET state = ?, completed_at = ? WHERE id = ?",
            (m.SubInvestigationState.abandoned.value, now_s, sub_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "sub_investigation_abandoned",
            f"Abandoned sub-investigation '{existing['scope']}': {reason}",
        )
        # Sync plan-item status: in_progress → abandoned.
        _set_plan_item_status(
            conn, dossier_id, _row_get(existing, "plan_item_id"), "abandoned",
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row)


# ---------- v2: InvestigationLog ----------
#
# The investigation_log is the typed, countable "evidence of work" surface
# (source_consulted, sub_investigation_spawned, etc.). It is *separate* from
# change_log (user-visit-diff) by design — appends here do NOT write to
# change_log. This keeps the "47 sources consulted" counter from polluting the
# since-last-visit plan-diff the user reads when they return.


def _row_to_investigation_log(row: sqlite3.Row) -> m.InvestigationLogEntry:
    return m.InvestigationLogEntry(
        id=row["id"],
        dossier_id=row["dossier_id"],
        work_session_id=row["work_session_id"],
        sub_investigation_id=row["sub_investigation_id"],
        entry_type=m.InvestigationLogEntryType(row["entry_type"]),
        payload=json.loads(row["payload"]) if row["payload"] else {},
        summary=row["summary"],
        created_at=_dt(row["created_at"]),
    )


def append_investigation_log(
    dossier_id: str,
    data: m.InvestigationLogAppend,
    work_session_id: Optional[str] = None,
) -> m.InvestigationLogEntry:
    now = m.utc_now()
    entry = m.InvestigationLogEntry(
        id=m.new_id("ilg"),
        dossier_id=dossier_id,
        work_session_id=work_session_id,
        sub_investigation_id=data.sub_investigation_id,
        entry_type=data.entry_type,
        payload=data.payload,
        summary=data.summary,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO investigation_log (id, dossier_id, work_session_id, sub_investigation_id,
                                           entry_type, payload, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                dossier_id,
                work_session_id,
                data.sub_investigation_id,
                data.entry_type.value,
                json.dumps(data.payload),
                data.summary,
                _dt_str(now),
            ),
        )
        # Note: intentionally do NOT call _log_change — see module-level comment.
    return entry


def list_investigation_log(
    dossier_id: str,
    entry_type: Optional[m.InvestigationLogEntryType] = None,
    limit: int = 500,
) -> list[m.InvestigationLogEntry]:
    q = "SELECT * FROM investigation_log WHERE dossier_id = ?"
    params: list[object] = [dossier_id]
    if entry_type is not None:
        q += " AND entry_type = ?"
        params.append(entry_type.value)
    q += " ORDER BY created_at LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(q, params).fetchall()
    return [_row_to_investigation_log(r) for r in rows]


def count_investigation_log_by_type(dossier_id: str) -> dict[str, int]:
    """Powers the "47 sources / 4 sub-investigations / 3 artifacts" header in the UI."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT entry_type, COUNT(*) AS n FROM investigation_log WHERE dossier_id = ? GROUP BY entry_type",
            (dossier_id,),
        ).fetchall()
    return {r["entry_type"]: r["n"] for r in rows}


# ---------- v2: ConsideredAndRejected ----------


def _row_to_considered_and_rejected(row: sqlite3.Row) -> m.ConsideredAndRejected:
    return m.ConsideredAndRejected(
        id=row["id"],
        dossier_id=row["dossier_id"],
        sub_investigation_id=row["sub_investigation_id"],
        path=row["path"],
        why_compelling=row["why_compelling"],
        why_rejected=row["why_rejected"],
        cost_of_error=row["cost_of_error"],
        sources=_SourceList.validate_json(row["sources"]),
        created_at=_dt(row["created_at"]),
    )


def add_considered_and_rejected(
    dossier_id: str,
    data: m.ConsideredAndRejectedCreate,
    work_session_id: Optional[str] = None,
) -> m.ConsideredAndRejected:
    now = m.utc_now()
    item = m.ConsideredAndRejected(
        id=m.new_id("crj"),
        dossier_id=dossier_id,
        sub_investigation_id=data.sub_investigation_id,
        path=data.path,
        why_compelling=data.why_compelling,
        why_rejected=data.why_rejected,
        cost_of_error=data.cost_of_error,
        sources=data.sources,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO considered_and_rejected
                (id, dossier_id, sub_investigation_id, path, why_compelling, why_rejected,
                 cost_of_error, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                dossier_id,
                data.sub_investigation_id,
                data.path,
                data.why_compelling,
                data.why_rejected,
                data.cost_of_error,
                _SourceList.dump_json(data.sources).decode(),
                _dt_str(now),
            ),
        )
        _log_change(
            conn, dossier_id, work_session_id, "considered_and_rejected_added",
            f"Rejected: {data.path}",
        )
        # Also append to investigation_log so the "paths considered" counter
        # reflects this. Inline insert keeps the timestamp inside the same txn.
        conn.execute(
            """
            INSERT INTO investigation_log (id, dossier_id, work_session_id, sub_investigation_id,
                                           entry_type, payload, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.new_id("ilg"),
                dossier_id,
                work_session_id,
                data.sub_investigation_id,
                m.InvestigationLogEntryType.path_rejected.value,
                json.dumps({"considered_and_rejected_id": item.id}),
                f"Rejected: {data.path}",
                _dt_str(now),
            ),
        )
        _touch_dossier(conn, dossier_id)
    return item


def list_considered_and_rejected(dossier_id: str) -> list[m.ConsideredAndRejected]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM considered_and_rejected WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_considered_and_rejected(r) for r in rows]


# ---------- day 3: computed dossier status ----------


def _decision_point_is_plan_approval(row: sqlite3.Row) -> bool:
    """Decide whether a decision_points row is a plan-approval gate.

    The plan-approval agent (running in parallel) is adding a ``kind`` column
    to ``decision_points``. When that column exists and is populated we trust
    it directly. Until then we fall back to a best-effort title heuristic:
    the title contains both "plan" AND "approve" (case-insensitive), or just
    "plan_approval"/"plan approval". Documented in the public function's
    docstring so callers know the fallback exists.
    """
    try:
        kind = row["kind"]
    except (IndexError, KeyError):
        kind = None
    if kind == "plan_approval":
        return True
    # kind missing (legacy row) or "generic" → fall back to title heuristic so
    # unclassified-but-obviously-plan-approval titles still trigger.
    title = (row["title"] or "").lower()
    if "plan_approval" in title or "plan approval" in title:
        return True
    return "plan" in title and ("approve" in title or "approval" in title)


def get_dossier_status(dossier_id: str) -> dict:
    """Single authoritative computed read for the dossier status indicator.

    Returns a dict with a ``status`` field whose value is determined by the
    following precedence (first match wins):

      1. ``delivered`` - ``dossier.status == delivered``
      2. ``running`` - orchestrator has an active run for this dossier
      3. ``waiting_plan_approval`` - plan has been drafted, is not approved,
         and there is an unresolved decision_point that is a plan-approval
         gate (see below for how that is identified).
      4. ``waiting_input`` - at least one unresolved needs_input OR at least
         one unresolved decision_point that is NOT a plan-approval gate.
      5. ``stuck`` - the most recent ``stuck_declared`` investigation_log
         entry is newer than ``last_visited_at`` (or within the last 24h if
         the dossier has never been visited).
      6. ``idle`` - none of the above.
      7. ``not_found`` - the dossier does not exist.

    The orchestrator check is guarded with a broad try/except so that a
    runtime import issue cannot take the status endpoint down.

    DecisionPoint.kind fallback: a parallel agent is adding a ``kind`` column
    to ``decision_points`` to distinguish plan-approval gates from regular
    decisions. When that column is present and populated we trust it
    (``kind == "plan_approval"``); when it is missing we fall back to a
    title heuristic - the title contains "plan_approval", "plan approval",
    or both "plan" AND "approve"/"approval" (case-insensitive).
    """
    dossier = get_dossier(dossier_id)
    if dossier is None:
        return {
            "dossier_id": dossier_id,
            "status": "not_found",
            "status_detail": "dossier not found",
            "active_work_session_id": None,
            "unresolved_plan_approval_id": None,
            "open_needs_input_count": 0,
            "open_decision_point_count": 0,
            "last_stuck_at": None,
            "delivered": False,
        }

    # Active work session (if any). Used to populate the response even when
    # the orchestrator does not report a "running" status (e.g. the run is
    # between turns, or we are on a different process).
    active_ws = get_active_work_session(dossier_id)
    active_ws_id = active_ws.id if active_ws else None

    # Gather unresolved decision_points and classify.
    with connect() as conn:
        dp_rows = conn.execute(
            "SELECT * FROM decision_points WHERE dossier_id = ? AND resolved_at IS NULL",
            (dossier_id,),
        ).fetchall()
        ni_rows = conn.execute(
            "SELECT id FROM needs_input WHERE dossier_id = ? AND answered_at IS NULL",
            (dossier_id,),
        ).fetchall()
        stuck_row = conn.execute(
            """
            SELECT created_at FROM investigation_log
             WHERE dossier_id = ? AND entry_type = ?
             ORDER BY created_at DESC LIMIT 1
            """,
            (dossier_id, m.InvestigationLogEntryType.stuck_declared.value),
        ).fetchone()

    unresolved_plan_approval_id: Optional[str] = None
    open_non_plan_dp_count = 0
    for row in dp_rows:
        if _decision_point_is_plan_approval(row):
            if unresolved_plan_approval_id is None:
                unresolved_plan_approval_id = row["id"]
        else:
            open_non_plan_dp_count += 1

    open_needs_input_count = len(ni_rows)
    last_stuck_at = _dt(stuck_row["created_at"]) if stuck_row else None

    delivered = dossier.status == m.DossierStatus.delivered

    # 1. delivered
    if delivered:
        status = "delivered"
        detail = "dossier is delivered"
    else:
        # 2. running (orchestrator)
        running = False
        try:
            from .agent.orchestrator import ORCHESTRATOR  # local import; guard below
            running = any(
                r.get("dossier_id") == dossier_id and r.get("status") == "running"
                for r in ORCHESTRATOR.list_active()
            )
        except Exception:  # noqa: BLE001 - status must not raise
            running = False

        if running:
            status = "running"
            detail = "agent is actively running"
        elif (
            dossier.investigation_plan is not None
            and dossier.investigation_plan.approved_at is None
            and unresolved_plan_approval_id is not None
        ):
            # 3. waiting_plan_approval
            status = "waiting_plan_approval"
            detail = "plan drafted; waiting for approval"
        elif open_needs_input_count > 0 or open_non_plan_dp_count > 0:
            # 4. waiting_input
            status = "waiting_input"
            parts = []
            if open_needs_input_count > 0:
                parts.append(f"{open_needs_input_count} open question(s)")
            if open_non_plan_dp_count > 0:
                parts.append(f"{open_non_plan_dp_count} unresolved decision(s)")
            detail = "waiting on: " + ", ".join(parts)
        elif last_stuck_at is not None and _stuck_is_recent(
            last_stuck_at, dossier.last_visited_at
        ):
            # 5. stuck
            status = "stuck"
            detail = "agent declared stuck and has not recovered"
        else:
            # 6. idle
            status = "idle"
            detail = "no active work"

    return {
        "dossier_id": dossier_id,
        "status": status,
        "status_detail": detail,
        "active_work_session_id": active_ws_id,
        "unresolved_plan_approval_id": unresolved_plan_approval_id,
        "open_needs_input_count": open_needs_input_count,
        "open_decision_point_count": open_non_plan_dp_count,
        "last_stuck_at": last_stuck_at,
        "delivered": delivered,
    }


def _stuck_is_recent(last_stuck_at: datetime, last_visited_at: Optional[datetime]) -> bool:
    """stuck wins if the most recent stuck_declared is after the user's last
    visit (they haven't seen it yet), or — if they've never visited — within
    the last 24h (so that a long-abandoned dossier doesn't stay "stuck"
    forever)."""
    from datetime import timedelta
    if last_visited_at is not None:
        return last_stuck_at > last_visited_at
    return (m.utc_now() - last_stuck_at) <= timedelta(hours=24)


# ---------- Sleep-mode wake state ----------


def set_dossier_wake_at(
    dossier_id: str,
    wake_at: datetime,
    reason: m.WakeReason,
) -> None:
    """Agent-initiated: schedule a future wake via schedule_wake tool.

    Overwrites any prior wake_at — the scheduler runs "earliest active wake
    wins," so repeated calls just reschedule. wake_pending stays clear; the
    scheduler will compare wake_at against now on its next tick.
    """
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET wake_at = ?, wake_reason = ? WHERE id = ?",
            (_dt_str(wake_at), reason.value, dossier_id),
        )


def mark_wake_pending(dossier_id: str, reason: m.WakeReason) -> None:
    """Signal that this dossier needs a scheduler pick-up on the next tick.

    Used by (a) reconcile_at_startup for crash-resume, (b) resolve_needs_input
    for reactive-wake, (c) resolve_decision_point if we extend reactive-wake
    there. Idempotent: repeated calls just leave the pending flag set.
    """
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET wake_pending = 1, wake_reason = ? WHERE id = ?",
            (reason.value, dossier_id),
        )


def clear_dossier_wake(dossier_id: str) -> None:
    """Clear both wake_at and wake_pending — called by the scheduler after
    successfully starting a run for this dossier. wake_reason is kept so
    logs/UI can still display "why we woke" for a short window.
    """
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET wake_at = NULL, wake_pending = 0 WHERE id = ?",
            (dossier_id,),
        )


def list_dossiers_ready_to_wake(now: Optional[datetime] = None) -> list[dict]:
    """Return dossiers the scheduler should pick up on its next tick.

    A dossier is ready if EITHER:
      * wake_pending = 1 (reactive / crash-resume / needs_input_resolved), OR
      * wake_at IS NOT NULL AND wake_at <= now (agent self-scheduled).

    Returns compact dicts (dossier_id, wake_at, wake_reason) — the scheduler
    does not need the full Dossier aggregate to decide what to start.
    """
    now_s = _dt_str(now or m.utc_now())
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id AS dossier_id, wake_at, wake_pending, wake_reason
              FROM dossiers
             WHERE wake_pending = 1
                OR (wake_at IS NOT NULL AND wake_at <= ?)
             ORDER BY COALESCE(wake_at, ''), id
            """,
            (now_s,),
        ).fetchall()
    return [
        {
            "dossier_id": r["dossier_id"],
            "wake_at": r["wake_at"],
            "wake_pending": bool(r["wake_pending"]),
            "wake_reason": r["wake_reason"],
        }
        for r in rows
    ]


def get_dossier_wake_state(dossier_id: str) -> Optional[dict]:
    """Read the current wake fields for a dossier. Returns None if not found."""
    with connect() as conn:
        row = conn.execute(
            "SELECT wake_at, wake_pending, wake_reason FROM dossiers WHERE id = ?",
            (dossier_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "wake_at": row["wake_at"],
        "wake_pending": bool(row["wake_pending"]),
        "wake_reason": row["wake_reason"],
    }


# ---------- Tool-invocation idempotency ----------


def get_tool_invocation(tool_use_id: str) -> Optional[dict]:
    """Return a previously-recorded tool_result for this tool_use_id, or None.

    The runtime calls this before dispatching a tool; if a hit, short-circuit
    and return the stored result — don't re-run the handler.
    """
    with connect() as conn:
        row = conn.execute(
            """
            SELECT tool_use_id, dossier_id, work_session_id, tool_name,
                   input_hash, result_json, is_error, created_at
              FROM tool_invocations
             WHERE tool_use_id = ?
            """,
            (tool_use_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "tool_use_id": row["tool_use_id"],
        "dossier_id": row["dossier_id"],
        "work_session_id": row["work_session_id"],
        "tool_name": row["tool_name"],
        "input_hash": row["input_hash"],
        "result_json": row["result_json"],
        "is_error": bool(row["is_error"]),
        "created_at": row["created_at"],
    }


def record_tool_invocation(
    tool_use_id: str,
    dossier_id: str,
    tool_name: str,
    input_hash: str,
    result_json: str,
    is_error: bool = False,
    work_session_id: Optional[str] = None,
) -> None:
    """Record a completed tool dispatch. INSERT OR IGNORE — a concurrent
    duplicate write (should be extremely rare in Path A) silently loses,
    which is the correct behavior for an idempotency spine.
    """
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO tool_invocations
              (tool_use_id, dossier_id, work_session_id, tool_name,
               input_hash, result_json, is_error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_use_id,
                dossier_id,
                work_session_id,
                tool_name,
                input_hash,
                result_json,
                1 if is_error else 0,
                _dt_str(m.utc_now()),
            ),
        )


# ---------- Budget accounting ----------


def _utc_day_str(dt: Optional[datetime] = None) -> str:
    dt = dt or m.utc_now()
    return dt.strftime("%Y-%m-%d")


def record_budget_usage(
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    day: Optional[str] = None,
) -> None:
    """Roll per-turn usage into the day's global budget row. UPSERT.

    `day` defaults to today (UTC). Tests may inject a specific date.
    """
    day_key = day or _utc_day_str()
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO budget_accounting (day, spent_usd, input_tokens, output_tokens, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(day) DO UPDATE SET
                spent_usd = spent_usd + excluded.spent_usd,
                input_tokens = input_tokens + excluded.input_tokens,
                output_tokens = output_tokens + excluded.output_tokens,
                updated_at = excluded.updated_at
            """,
            (day_key, float(cost_usd), int(input_tokens), int(output_tokens), now_s),
        )


def get_budget_today() -> m.BudgetRollup:
    """Return today's rollup, synthesizing a zero row if no spend yet."""
    day_key = _utc_day_str()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM budget_accounting WHERE day = ?", (day_key,)
        ).fetchone()
    if row is None:
        return m.BudgetRollup(day=day_key, updated_at=m.utc_now())
    return m.BudgetRollup(
        day=row["day"],
        spent_usd=float(row["spent_usd"]),
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        updated_at=_dt(row["updated_at"]),
    )


def list_budget_range(start_day: str, end_day: str) -> list[m.BudgetRollup]:
    """Inclusive range, ordered by day ascending. Day strings in YYYY-MM-DD."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM budget_accounting WHERE day >= ? AND day <= ? ORDER BY day",
            (start_day, end_day),
        ).fetchall()
    return [
        m.BudgetRollup(
            day=r["day"],
            spent_usd=float(r["spent_usd"]),
            input_tokens=int(r["input_tokens"]),
            output_tokens=int(r["output_tokens"]),
            updated_at=_dt(r["updated_at"]),
        )
        for r in rows
    ]


# ---------- Settings ----------


def get_setting(key: str, default=None):
    """Return the JSON-decoded value for `key`, or `default` if not set."""
    with connect() as conn:
        row = conn.execute(
            "SELECT value_json FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return default
    return json.loads(row["value_json"])


def set_setting(key: str, value) -> m.Setting:
    """UPSERT a setting. Value is JSON-encoded. Returns the stored row."""
    now_s = _dt_str(m.utc_now())
    blob = json.dumps(value)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, blob, now_s),
        )
    return m.Setting(key=key, value=value, updated_at=m.utc_now())


def list_settings() -> list[m.Setting]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value_json, updated_at FROM settings ORDER BY key"
        ).fetchall()
    return [
        m.Setting(
            key=r["key"],
            value=json.loads(r["value_json"]),
            updated_at=_dt(r["updated_at"]),
        )
        for r in rows
    ]


def seed_default_settings(defaults: dict) -> None:
    """Insert missing defaults only — never overwrite an edited value.

    Called from init_db / lifespan startup to guarantee the UI has something
    to show. `defaults` maps setting key -> default value (any JSON-serializable).
    """
    with connect() as conn:
        for key, value in defaults.items():
            row = conn.execute(
                "SELECT 1 FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row is not None:
                continue
            conn.execute(
                "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), _dt_str(m.utc_now())),
            )


# ---------- Session summaries (Phase 3) ----------


def save_session_summary(data: m.SessionSummary) -> m.SessionSummary:
    """UPSERT on session_id. created_at on insert is preserved on conflict.

    The happy path is a single INSERT: the agent calls summarize_session once
    near end-of-session and this writes the row. The runtime fallback may
    race against the agent call if a turn overruns; ON CONFLICT preserves
    whichever reached storage first, with a best-effort update of narrative
    fields so a real summary isn't clobbered by the empty fallback.
    """
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO session_summaries
                (session_id, dossier_id, summary, confirmed, ruled_out,
                 blocked_on, questions_advanced, recommended_next_action,
                 cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary = CASE
                    WHEN excluded.summary != '' THEN excluded.summary
                    ELSE session_summaries.summary
                END,
                confirmed = CASE
                    WHEN excluded.confirmed != '[]' THEN excluded.confirmed
                    ELSE session_summaries.confirmed
                END,
                ruled_out = CASE
                    WHEN excluded.ruled_out != '[]' THEN excluded.ruled_out
                    ELSE session_summaries.ruled_out
                END,
                blocked_on = CASE
                    WHEN excluded.blocked_on != '[]' THEN excluded.blocked_on
                    ELSE session_summaries.blocked_on
                END,
                questions_advanced = CASE
                    WHEN excluded.questions_advanced != '[]' THEN excluded.questions_advanced
                    ELSE session_summaries.questions_advanced
                END,
                recommended_next_action = COALESCE(
                    excluded.recommended_next_action,
                    session_summaries.recommended_next_action
                ),
                cost_usd = excluded.cost_usd
            """,
            (
                data.session_id,
                data.dossier_id,
                data.summary,
                json.dumps(data.confirmed),
                json.dumps(data.ruled_out),
                json.dumps(data.blocked_on),
                json.dumps(data.questions_advanced),
                data.recommended_next_action,
                float(data.cost_usd),
                _dt_str(data.created_at),
            ),
        )
    return data


def get_session_summary(session_id: str) -> Optional[m.SessionSummary]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return _row_to_session_summary(row) if row else None


def list_session_summaries_for_dossier(dossier_id: str) -> list[m.SessionSummary]:
    """All session summaries for a dossier, ordered by created_at ascending
    (oldest first; the UI reverses for "most recent session at top")."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM session_summaries WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_session_summary(r) for r in rows]


def _row_to_session_summary(row: sqlite3.Row) -> m.SessionSummary:
    return m.SessionSummary(
        session_id=row["session_id"],
        dossier_id=row["dossier_id"],
        summary=row["summary"] or "",
        confirmed=_json_list(row["confirmed"]),
        ruled_out=_json_list(row["ruled_out"]),
        blocked_on=_json_list(row["blocked_on"]),
        questions_advanced=_json_list(_row_get(row, "questions_advanced") or "[]"),
        recommended_next_action=row["recommended_next_action"],
        cost_usd=float(row["cost_usd"] or 0.0),
        created_at=_dt(row["created_at"]),
    )
