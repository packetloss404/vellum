"""Plan items CRUD — first-class table replacing the JSON blob in dossiers.investigation_plan."""
from __future__ import annotations

import json
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import _dt, _dt_str, _json_list, _touch_dossier


def _row_to_plan_item(row) -> m.PlanItem:
    return m.PlanItem(
        id=row["id"],
        dossier_id=row["dossier_id"],
        question=row["question"],
        rationale=row["rationale"] or "",
        expected_sources=_json_list(row["expected_sources"]),
        as_sub_investigation=bool(row["as_sub_investigation"]),
        status=m.PlanItemStatus(row["status"]),
        order_key=row["order_key"],
        sub_investigation_id=row["sub_investigation_id"],
        blocked_reason=row["blocked_reason"],
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def list_plan_items(dossier_id: str) -> list[m.PlanItem]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM plan_items WHERE dossier_id = ? ORDER BY order_key",
            (dossier_id,),
        ).fetchall()
    return [_row_to_plan_item(r) for r in rows]


def list_plan_items_with_conn(conn, dossier_id: str) -> list[m.PlanItem]:
    rows = conn.execute(
        "SELECT * FROM plan_items WHERE dossier_id = ? ORDER BY order_key",
        (dossier_id,),
    ).fetchall()
    return [_row_to_plan_item(r) for r in rows]


def get_plan_item(dossier_id: str, plan_item_id: str) -> Optional[m.PlanItem]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM plan_items WHERE dossier_id = ? AND plan_item_id = ?",
            (dossier_id, plan_item_id),
        ).fetchone()
    return _row_to_plan_item(row) if row else None


def get_plan_item_by_id(plan_item_id: str) -> Optional[m.PlanItem]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM plan_items WHERE id = ?",
            (plan_item_id,),
        ).fetchone()
    return _row_to_plan_item(row) if row else None


def get_plan_item_by_id_with_conn(conn, plan_item_id: str) -> Optional[m.PlanItem]:
    row = conn.execute(
        "SELECT * FROM plan_items WHERE id = ?",
        (plan_item_id,),
    ).fetchone()
    return _row_to_plan_item(row) if row else None


def upsert_plan_item(dossier_id: str, item: m.PlanItem) -> m.PlanItem:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO plan_items (id, dossier_id, plan_item_id, question, rationale,
                                    expected_sources, as_sub_investigation, status,
                                    order_key, sub_investigation_id, blocked_reason,
                                    created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dossier_id, plan_item_id) DO UPDATE SET
                question = excluded.question,
                rationale = excluded.rationale,
                expected_sources = excluded.expected_sources,
                as_sub_investigation = excluded.as_sub_investigation,
                status = excluded.status,
                order_key = excluded.order_key,
                sub_investigation_id = excluded.sub_investigation_id,
                blocked_reason = excluded.blocked_reason,
                updated_at = excluded.updated_at
            """,
            (
                item.id,
                dossier_id,
                item.id,
                item.question,
                item.rationale,
                json.dumps(item.expected_sources),
                int(item.as_sub_investigation),
                item.status.value if isinstance(item.status, m.PlanItemStatus) else item.status,
                item.order_key,
                item.sub_investigation_id,
                item.blocked_reason,
                now_s,
                now_s,
            ),
        )
        _touch_dossier(conn, dossier_id)
    return get_plan_item(dossier_id, item.id) or item


def upsert_plan_item_with_conn(conn, dossier_id: str, item: m.PlanItem) -> m.PlanItem:
    now_s = _dt_str(m.utc_now())
    conn.execute(
        """
        INSERT INTO plan_items (id, dossier_id, plan_item_id, question, rationale,
                                expected_sources, as_sub_investigation, status,
                                order_key, sub_investigation_id, blocked_reason,
                                created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dossier_id, plan_item_id) DO UPDATE SET
            question = excluded.question,
            rationale = excluded.rationale,
            expected_sources = excluded.expected_sources,
            as_sub_investigation = excluded.as_sub_investigation,
            status = excluded.status,
            order_key = excluded.order_key,
            sub_investigation_id = excluded.sub_investigation_id,
            blocked_reason = excluded.blocked_reason,
            updated_at = excluded.updated_at
        """,
        (
            item.id,
            dossier_id,
            item.id,
            item.question,
            item.rationale,
            json.dumps(item.expected_sources),
            int(item.as_sub_investigation),
            item.status.value if isinstance(item.status, m.PlanItemStatus) else item.status,
            item.order_key,
            item.sub_investigation_id,
            item.blocked_reason,
            now_s,
            now_s,
        ),
    )
    row = conn.execute(
        "SELECT * FROM plan_items WHERE dossier_id = ? AND plan_item_id = ?",
        (dossier_id, item.id),
    ).fetchone()
    return _row_to_plan_item(row) if row else item


def bulk_replace_plan_items(dossier_id: str, items: list[m.PlanItem]) -> list[m.PlanItem]:
    with connect() as conn:
        conn.execute(
            "DELETE FROM plan_items WHERE dossier_id = ?", (dossier_id,)
        )
        for idx, item in enumerate(items):
            now_s = _dt_str(m.utc_now())
            item_with_order = item.model_copy(update={
                "order_key": item.order_key if item.order_key != 0.0 else (idx + 1) * 10.0,
                "dossier_id": dossier_id,
            })
            conn.execute(
                """
                INSERT INTO plan_items (id, dossier_id, plan_item_id, question, rationale,
                                        expected_sources, as_sub_investigation, status,
                                        order_key, sub_investigation_id, blocked_reason,
                                        created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_with_order.id,
                    dossier_id,
                    item_with_order.id,
                    item_with_order.question,
                    item_with_order.rationale,
                    json.dumps(item_with_order.expected_sources),
                    int(item_with_order.as_sub_investigation),
                    item_with_order.status.value if isinstance(item_with_order.status, m.PlanItemStatus) else item_with_order.status,
                    item_with_order.order_key,
                    item_with_order.sub_investigation_id,
                    item_with_order.blocked_reason,
                    now_s,
                    now_s,
                ),
            )
        _touch_dossier(conn, dossier_id)
    return list_plan_items(dossier_id)


def bulk_replace_plan_items_with_conn(
    conn, dossier_id: str, items: list[m.PlanItem]
) -> list[m.PlanItem]:
    conn.execute(
        "DELETE FROM plan_items WHERE dossier_id = ?", (dossier_id,)
    )
    for idx, item in enumerate(items):
        now_s = _dt_str(m.utc_now())
        item_with_order = item.model_copy(update={
            "order_key": item.order_key if item.order_key != 0.0 else (idx + 1) * 10.0,
            "dossier_id": dossier_id,
        })
        conn.execute(
            """
            INSERT INTO plan_items (id, dossier_id, plan_item_id, question, rationale,
                                    expected_sources, as_sub_investigation, status,
                                    order_key, sub_investigation_id, blocked_reason,
                                    created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_with_order.id,
                dossier_id,
                item_with_order.id,
                item_with_order.question,
                item_with_order.rationale,
                json.dumps(item_with_order.expected_sources),
                int(item_with_order.as_sub_investigation),
                item_with_order.status.value if isinstance(item_with_order.status, m.PlanItemStatus) else item_with_order.status,
                item_with_order.order_key,
                item_with_order.sub_investigation_id,
                item_with_order.blocked_reason,
                now_s,
                now_s,
            ),
        )
    rows = conn.execute(
        "SELECT * FROM plan_items WHERE dossier_id = ? ORDER BY order_key",
        (dossier_id,),
    ).fetchall()
    return [_row_to_plan_item(r) for r in rows]


def set_plan_item_status(
    dossier_id: str,
    plan_item_id: str,
    status: str,
    sub_investigation_id: Optional[str] = None,
    blocked_reason: Optional[str] = None,
) -> Optional[m.PlanItem]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        set_parts = ["status = ?", "updated_at = ?"]
        values: list[object] = [status, now_s]
        if sub_investigation_id is not None:
            set_parts.append("sub_investigation_id = ?")
            values.append(sub_investigation_id)
        if blocked_reason is not None:
            set_parts.append("blocked_reason = ?")
            values.append(blocked_reason)
        values.extend([dossier_id, plan_item_id])
        cur = conn.execute(
            f"UPDATE plan_items SET {', '.join(set_parts)} "
            "WHERE dossier_id = ? AND plan_item_id = ?",
            values,
        )
        if cur.rowcount == 0:
            return None
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM plan_items WHERE dossier_id = ? AND plan_item_id = ?",
            (dossier_id, plan_item_id),
        ).fetchone()
    return _row_to_plan_item(row) if row else None


def set_plan_item_status_with_conn(
    conn,
    dossier_id: str,
    plan_item_id: str,
    status: str,
    sub_investigation_id: Optional[str] = None,
    blocked_reason: Optional[str] = None,
) -> Optional[m.PlanItem]:
    now_s = _dt_str(m.utc_now())
    set_parts = ["status = ?", "updated_at = ?"]
    values: list[object] = [status, now_s]
    if sub_investigation_id is not None:
        set_parts.append("sub_investigation_id = ?")
        values.append(sub_investigation_id)
    if blocked_reason is not None:
        set_parts.append("blocked_reason = ?")
        values.append(blocked_reason)
    values.extend([dossier_id, plan_item_id])
    cur = conn.execute(
        f"UPDATE plan_items SET {', '.join(set_parts)} "
        "WHERE dossier_id = ? AND plan_item_id = ?",
        values,
    )
    if cur.rowcount == 0:
        return None
    row = conn.execute(
        "SELECT * FROM plan_items WHERE dossier_id = ? AND plan_item_id = ?",
        (dossier_id, plan_item_id),
    ).fetchone()
    return _row_to_plan_item(row) if row else None


def delete_plan_items_for_dossier(dossier_id: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM plan_items WHERE dossier_id = ?", (dossier_id,)
        )
        return cur.rowcount
