import hashlib
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from vellum.ops.sqlite_backup import (
    BackupError,
    backup_database,
    restore_database,
    verify_backup,
)


def _rows(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as conn:
        return [row[0] for row in conn.execute("SELECT value FROM records ORDER BY value")]


def _database(path: Path, values: tuple[str, ...]) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE records (value TEXT NOT NULL)")
        conn.executemany("INSERT INTO records VALUES (?)", ((value,) for value in values))
        conn.commit()


def test_online_backup_is_consistent_and_has_verified_manifests(tmp_path: Path) -> None:
    live = tmp_path / "live.sqlite3"
    backup = tmp_path / "backups" / "snapshot.sqlite3"
    _database(live, ("a", "b"))

    # Keep a WAL connection open while taking the snapshot; sqlite.backup must
    # still include the committed WAL contents in the single output database.
    with closing(sqlite3.connect(live)) as conn:
        conn.execute("INSERT INTO records VALUES ('c')")
        conn.commit()
        result = backup_database(live, backup)

    assert _rows(backup) == ["a", "b", "c"]
    assert result.integrity == "ok"
    assert Path(result.checksum_file).read_text().startswith(result.checksum)
    assert verify_backup(backup).checksum == result.checksum


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are enforced in production")
def test_backup_artifacts_and_directory_are_private(tmp_path: Path) -> None:
    live = tmp_path / "live.sqlite3"
    backup = tmp_path / "backups" / "snapshot.sqlite3"
    _database(live, ("private",))

    result = backup_database(live, backup)

    assert backup.parent.stat().st_mode & 0o777 == 0o700
    for path in (backup, Path(result.checksum_file), Path(result.metadata_file)):
        assert path.stat().st_mode & 0o777 == 0o600


def test_verify_rejects_a_changed_backup(tmp_path: Path) -> None:
    live = tmp_path / "live.sqlite3"
    backup = tmp_path / "snapshot.sqlite3"
    _database(live, ("original",))
    backup_database(live, backup)

    with backup.open("ab") as handle:
        handle.write(b"tampered")

    with pytest.raises(BackupError, match="checksum mismatch"):
        verify_backup(backup)


def test_restore_requires_exact_confirmation_and_preserves_old_database(
    tmp_path: Path,
) -> None:
    live = tmp_path / "live.sqlite3"
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "snapshot.sqlite3"
    _database(live, ("before",))
    _database(source, ("after",))
    backup_database(source, backup)

    with pytest.raises(BackupError, match="confirm-replace"):
        restore_database(
            backup,
            live,
            confirm_replace=str(tmp_path / "wrong.sqlite3"),
            confirm_backend_stopped=True,
        )

    with pytest.raises(BackupError, match="confirm-backend-stopped"):
        restore_database(
            backup,
            live,
            confirm_replace=str(live.resolve()),
            confirm_backend_stopped=False,
        )

    restored, preserved = restore_database(
        backup,
        live,
        confirm_replace=str(live.resolve()),
        confirm_backend_stopped=True,
        pre_restore_dir=tmp_path / "pre-restore",
    )

    assert _rows(live) == ["after"]
    assert _rows(Path(preserved.database)) == ["before"]
    assert restored.checksum == hashlib.sha256(backup.read_bytes()).hexdigest()
    assert Path(preserved.checksum_file).exists()
