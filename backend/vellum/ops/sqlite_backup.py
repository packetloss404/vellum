"""Verified online backup and guarded restore for Vellum's SQLite database.

The backup path uses SQLite's online backup API, so a running WAL-mode database
is copied as one consistent snapshot. Restores deliberately require the API to
be stopped and an exact destination-path confirmation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from vellum import config


class BackupError(RuntimeError):
    """Raised when a backup or restore cannot be completed safely."""


@dataclass(frozen=True)
class BackupResult:
    database: str
    checksum: str
    checksum_file: str
    metadata_file: str
    size_bytes: int
    integrity: str


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    # Windows rejects fsync on a read-only descriptor.
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _atomic_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(
            descriptor, "w", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _integrity_check(path: Path) -> tuple[str, int, int]:
    uri = path.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=10.0)) as conn:
        rows = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
        if rows != ["ok"]:
            raise BackupError(f"SQLite integrity check failed for {path}: {rows!r}")
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    return "ok", page_count, user_version


def _write_manifest(database: Path, source: Path) -> BackupResult:
    integrity, page_count, user_version = _integrity_check(database)
    checksum = _sha256(database)
    checksum_path = database.with_suffix(database.suffix + ".sha256")
    metadata_path = database.with_suffix(database.suffix + ".json")
    _atomic_text(checksum_path, f"{checksum}  {database.name}\n")
    metadata = {
        "format": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "database": database.name,
        "sha256": checksum,
        "size_bytes": database.stat().st_size,
        "page_count": page_count,
        "sqlite_user_version": user_version,
        "integrity_check": integrity,
    }
    _atomic_text(metadata_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return BackupResult(
        database=str(database),
        checksum=checksum,
        checksum_file=str(checksum_path),
        metadata_file=str(metadata_path),
        size_bytes=database.stat().st_size,
        integrity=integrity,
    )


def backup_database(database: Path, output: Path) -> BackupResult:
    """Create and verify a transactionally consistent backup at *output*."""

    source = database.resolve(strict=True)
    destination = output.resolve()
    if source == destination:
        raise BackupError("backup destination must differ from the live database")
    _private_dir(destination.parent)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        os.close(descriptor)
        source_uri = source.as_uri() + "?mode=ro"
        with closing(
            sqlite3.connect(source_uri, uri=True, timeout=30.0)
        ) as source_conn:
            with closing(sqlite3.connect(temporary, timeout=30.0)) as target_conn:
                source_conn.backup(target_conn)
        _integrity_check(temporary)
        _fsync_file(temporary)
        os.replace(temporary, destination)
        destination.chmod(0o600)
        return _write_manifest(destination, source)
    except (OSError, sqlite3.Error) as exc:
        raise BackupError(f"could not back up {source} to {destination}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def verify_backup(database: Path, *, require_checksum: bool = True) -> BackupResult:
    """Validate a backup's SHA-256 sidecar and full SQLite integrity."""

    backup = database.resolve(strict=True)
    checksum_path = backup.with_suffix(backup.suffix + ".sha256")
    actual = _sha256(backup)
    if checksum_path.exists():
        fields = checksum_path.read_text(encoding="utf-8").strip().split()
        if not fields or fields[0].lower() != actual:
            raise BackupError(f"checksum mismatch for {backup}")
    elif require_checksum:
        raise BackupError(f"checksum sidecar is missing: {checksum_path}")

    integrity, _, _ = _integrity_check(backup)
    metadata_path = backup.with_suffix(backup.suffix + ".json")
    return BackupResult(
        database=str(backup),
        checksum=actual,
        checksum_file=str(checksum_path),
        metadata_file=str(metadata_path),
        size_bytes=backup.stat().st_size,
        integrity=integrity,
    )


def _prepare_destination_for_restore(destination: Path) -> None:
    """Checkpoint WAL and prove that no other process holds the database."""

    try:
        with closing(
            sqlite3.connect(destination, timeout=1.0, isolation_level=None)
        ) as conn:
            conn.execute("PRAGMA busy_timeout=1000")
            conn.execute("BEGIN EXCLUSIVE")
            conn.execute("ROLLBACK")
            busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if busy:
                raise BackupError(
                    "database is busy; stop the backend before restoring"
                )
    except sqlite3.Error as exc:
        raise BackupError(
            f"cannot lock {destination}; stop the backend before restoring: {exc}"
        ) from exc


def restore_database(
    backup: Path,
    destination: Path,
    *,
    confirm_replace: str,
    confirm_backend_stopped: bool,
    pre_restore_dir: Path | None = None,
) -> tuple[BackupResult, BackupResult]:
    """Atomically restore *backup* after preserving the existing destination."""

    if not confirm_backend_stopped:
        raise BackupError(
            "refusing restore: pass --confirm-backend-stopped after stopping the API"
        )
    source = backup.resolve(strict=True)
    target = destination.resolve(strict=True)
    try:
        confirmed = Path(confirm_replace).expanduser().resolve(strict=True)
    except OSError as exc:
        raise BackupError(
            "--confirm-replace must name the existing destination"
        ) from exc
    if confirmed != target:
        raise BackupError(
            f"refusing restore: --confirm-replace must equal {target} exactly"
        )
    if source == target:
        raise BackupError("backup and restore destination must differ")

    verify_backup(source)
    _prepare_destination_for_restore(target)

    archive_dir = (pre_restore_dir or (target.parent / "backups")).resolve()
    _private_dir(archive_dir)
    pre_restore = archive_dir / (
        f"{target.stem}.pre-restore.{_timestamp()}{target.suffix or '.sqlite3'}"
    )
    preserved = backup_database(target, pre_restore)

    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.restore")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with source.open("rb") as read_handle, os.fdopen(
            descriptor, "wb"
        ) as write_handle:
            shutil.copyfileobj(read_handle, write_handle, 1024 * 1024)
            write_handle.flush()
            os.fsync(write_handle.fileno())
        _integrity_check(temporary)
        os.replace(temporary, target)
        target.chmod(0o600)
        # These files belong to the old database generation. The exclusive
        # lock/checkpoint above ensures they are not live before removal.
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(target) + suffix).unlink(missing_ok=True)
        restored = verify_backup(target, require_checksum=False)
    except (OSError, sqlite3.Error) as exc:
        raise BackupError(
            f"restore failed; original preserved at {preserved.database}: {exc}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return restored, preserved


def _default_backup_path(output_dir: Path) -> Path:
    return output_dir / f"vellum.{_timestamp()}.sqlite3"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    backup_cmd = commands.add_parser("backup", help="create an online backup")
    backup_cmd.add_argument("--database", type=Path, default=config.DB_PATH)
    output = backup_cmd.add_mutually_exclusive_group()
    output.add_argument("--output", type=Path)
    output.add_argument("--output-dir", type=Path, default=Path("backups"))

    verify_cmd = commands.add_parser("verify", help="verify a backup and checksum")
    verify_cmd.add_argument("backup", type=Path)

    restore_cmd = commands.add_parser("restore", help="replace a stopped database")
    restore_cmd.add_argument("backup", type=Path)
    restore_cmd.add_argument("--database", type=Path, default=config.DB_PATH)
    restore_cmd.add_argument("--confirm-replace", required=True)
    restore_cmd.add_argument("--confirm-backend-stopped", action="store_true")
    restore_cmd.add_argument("--pre-restore-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "backup":
            output = args.output or _default_backup_path(args.output_dir)
            result: object = asdict(backup_database(args.database, output))
        elif args.command == "verify":
            result = asdict(verify_backup(args.backup))
        else:
            restored, preserved = restore_database(
                args.backup,
                args.database,
                confirm_replace=args.confirm_replace,
                confirm_backend_stopped=args.confirm_backend_stopped,
                pre_restore_dir=args.pre_restore_dir,
            )
            result = {"restored": asdict(restored), "pre_restore": asdict(preserved)}
    except (BackupError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
