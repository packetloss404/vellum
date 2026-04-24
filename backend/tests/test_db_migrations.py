from __future__ import annotations

import sqlite3

import pytest


def _create_legacy_decision_points_table(db_path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE decision_points (
                id TEXT PRIMARY KEY,
                dossier_id TEXT NOT NULL,
                title TEXT NOT NULL,
                options TEXT NOT NULL DEFAULT '[]',
                recommendation TEXT NOT NULL DEFAULT '',
                blocks_section_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                chosen TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_init_db_adds_decision_point_kind_to_legacy_table(tmp_path):
    from vellum import db

    db_path = tmp_path / "legacy.db"
    _create_legacy_decision_points_table(db_path)

    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(decision_points)")}
    finally:
        conn.close()

    assert "kind" in columns


def test_init_db_backfills_legacy_plan_approval_decision_points(tmp_path):
    from vellum import db

    db_path = tmp_path / "legacy.db"
    _create_legacy_decision_points_table(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO decision_points (
                id, dossier_id, title, options, recommendation,
                blocks_section_ids, created_at
            )
            VALUES (?, 'dos_1', ?, '[]', '', '[]', '2026-01-01T00:00:00+00:00')
            """,
            [
                ("dp_plan", "Approve investigation plan?"),
                ("dp_generic", "Choose vendor"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        rows = dict(conn.execute("SELECT id, kind FROM decision_points").fetchall())
    finally:
        conn.close()

    assert rows["dp_plan"] == "plan_approval"
    assert rows["dp_generic"] == "generic"


def test_init_db_closes_duplicate_unresolved_plan_approvals(tmp_path):
    from vellum import db

    db_path = tmp_path / "legacy.db"
    _create_legacy_decision_points_table(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO decision_points (
                id, dossier_id, title, options, recommendation,
                blocks_section_ids, created_at
            )
            VALUES (?, ?, ?, '[]', '', '[]', ?)
            """,
            [
                ("dp_old", "dos_1", "Approve investigation plan?", "2026-01-01T00:00:00+00:00"),
                ("dp_new", "dos_1", "Approve investigation plan?", "2026-01-02T00:00:00+00:00"),
                ("dp_generic", "dos_1", "Choose vendor", "2026-01-03T00:00:00+00:00"),
                ("dp_other", "dos_2", "Approve investigation plan?", "2026-01-04T00:00:00+00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        rows = {
            row[0]: (row[1], row[2])
            for row in conn.execute("SELECT id, kind, resolved_at FROM decision_points")
        }
        open_plan_dos_1 = conn.execute(
            """
            SELECT id FROM decision_points
             WHERE dossier_id = 'dos_1'
               AND kind = 'plan_approval'
               AND resolved_at IS NULL
            """
        ).fetchall()
        index = conn.execute(
            """
            SELECT name FROM sqlite_master
             WHERE type = 'index'
               AND name = 'idx_decision_points_one_open_plan_approval_per_dossier'
            """
        ).fetchone()
    finally:
        conn.close()

    assert [row[0] for row in open_plan_dos_1] == ["dp_new"]
    assert rows["dp_old"][1] is not None
    assert rows["dp_generic"] == ("generic", None)
    assert rows["dp_other"] == ("plan_approval", None)
    assert index is not None


def test_open_plan_approval_unique_index_rejects_duplicates(tmp_path):
    from vellum import db

    db_path = tmp_path / "current.db"
    db.init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO decision_points (
                id, dossier_id, title, options, recommendation,
                blocks_section_ids, kind, created_at
            )
            VALUES ('dp_one', 'dos_1', 'Approve plan?', '[]', '', '[]',
                    'plan_approval', '2026-01-01T00:00:00+00:00')
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO decision_points (
                    id, dossier_id, title, options, recommendation,
                    blocks_section_ids, kind, created_at
                )
                VALUES ('dp_two', 'dos_1', 'Approve plan?', '[]', '', '[]',
                        'plan_approval', '2026-01-02T00:00:00+00:00')
                """
            )
    finally:
        conn.close()
