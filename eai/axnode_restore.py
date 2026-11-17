"""One durable SQLite commit owns an isolated AXNODE epoch and its selection.

The coordinator has sole ownership of the captured images and node bytes.
Its log selects a complete epoch or no epoch. It never attaches, replaces,
migrates or activates any source or live DB. The private local directory
must have a trusted owner and a filesystem honoring SQLite's sync requests.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import re
import sqlite3
import stat
import tempfile

from .axnode_epoch import IsolatedEpochPayload, _DATABASE_FILES, _offline_sqlite_image
from .axnode_maintenance import _MAX_ARCHIVE_BYTES, _MAX_NODES
from .axnode_schema import MAX_NODE_BYTES
from .axnode_sidecar_backup import _MAX_DB
from .axnode_store import AXNodeStore
from .contracts import canonical_bytes
from .sidecar_coherence_review import capture_isolated_write_epoch

_RECOVERY_DIR_PREFIX = "eai-isolated-recovery-"
_RECOVERY_DB = "epoch.sqlite"
_APPLICATION_ID = 0x45414952  # EAIR
_MAX_LEDGER_BYTES = 512 * 1024 * 1024
_ROLLBACK_RESERVE_BYTES = 2 * 1024 * 1024
_MAX_PAYLOAD_BYTES = _MAX_ARCHIVE_BYTES + 2 * _MAX_DB
_MAX_REVISIONS = 1024
_OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SCHEMA = {
    "source_binding": """CREATE TABLE source_binding (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        source_sha256 TEXT NOT NULL
    )""",
    "transitions": """CREATE TABLE transitions (
        revision INTEGER PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE,
        action TEXT NOT NULL,
        prior_epoch INTEGER REFERENCES transitions(revision),
        epoch INTEGER REFERENCES transitions(revision),
        checkpoint_sha256 TEXT,
        payload_sha256 TEXT,
        CHECK ((action = 'PUBLISH' AND epoch IS revision
                    AND checkpoint_sha256 IS NOT NULL AND payload_sha256 IS NOT NULL)
            OR (action = 'ROLLBACK' AND prior_epoch IS NOT NULL
                    AND checkpoint_sha256 IS NULL AND payload_sha256 IS NULL))
    )""",
    "epoch_files": """CREATE TABLE epoch_files (
        revision INTEGER NOT NULL REFERENCES transitions(revision),
        name TEXT NOT NULL,
        content BLOB NOT NULL,
        PRIMARY KEY (revision, name)
    ) WITHOUT ROWID""",
}


@dataclass(frozen=True)
class IsolatedRestoreRequest:
    recovery_root: str | Path
    operation_id: str
    expected_revision: int
    reviewed_checkpoint_sha256: str
    allow_isolated_write: bool = False


@dataclass(frozen=True)
class IsolatedRestoreReceipt:
    """The result of one operation at its recorded revision, even on replay."""

    status: str
    revision: int
    epoch_revision: int | None
    checkpoint_sha256: str | None
    payload_sha256: str | None


@dataclass(frozen=True)
class IsolatedRestoreState:
    revision: int
    epoch_revision: int | None
    checkpoint_sha256: str | None
    payload_sha256: str | None
    payload: IsolatedEpochPayload | None


@dataclass(frozen=True)
class _Transition:
    revision: int
    operation_id: str
    action: str
    prior_epoch: int | None
    epoch: int | None
    checkpoint_sha256: str | None = None
    payload_sha256: str | None = None


def _private_directory(location: str | Path) -> Path:
    path = Path(location).expanduser().absolute()
    if path.drive.startswith("\\\\") or path.is_reserved() or ".." in path.parts:
        raise ValueError("isolated recovery requires a local directory")
    for directory in (*reversed(path.parents), path):
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError("isolated recovery requires unlinked directories")
    return path.resolve(strict=True)


def _private_files(root: Path) -> Path:
    database = root / _RECOVERY_DB
    allowed = {database.name, database.name + "-journal"}
    if not root.name.startswith(_RECOVERY_DIR_PREFIX):
        raise ValueError("dedicated isolated recovery directory required")
    _outside_axnode_store(root)
    for entry in root.iterdir():
        try:
            info = entry.lstat()
        except FileNotFoundError:
            # A transaction on another connection may just have committed.
            if entry.name == database.name + "-journal":
                continue
            raise
        if (entry.name not in allowed or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError("unexpected or linked isolated recovery file")
    with database.open("rb") as handle:
        header = handle.read(100)
    if (len(header) != 100 or header[:16] != b"SQLite format 3\x00"
            or header[18:20] != b"\x01\x01"
            or int.from_bytes(header[68:72], "big") != _APPLICATION_ID
            or int.from_bytes(header[60:64], "big") != 1
            or database.stat().st_size > _MAX_LEDGER_BYTES):
        raise ValueError("unrecognized or oversized isolated recovery database")
    return database


def _outside_axnode_store(root: Path) -> None:
    for directory in (root, *root.parents):
        catalog = directory / "axnodes.sqlite"
        if catalog.exists() or catalog.is_symlink():
            raise PermissionError("recovery location is inside an existing AXNODE store")


def _source_sha(store: AXNodeStore) -> str:
    if type(store) is not AXNodeStore:
        raise ValueError("explicit originating AXNODE store required")
    return hashlib.sha256(os.fsencode(os.path.normcase(store.root))).hexdigest()


def _require_write_permission(allowed: bool) -> None:
    if allowed is not True:
        raise PermissionError("explicit isolated recovery write option required")


def _configure_database(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=EXTRA")
    journal_mode = db.execute("PRAGMA journal_mode").fetchone()
    sync_level = db.execute("PRAGMA synchronous").fetchone()
    if journal_mode != ("delete",) or sync_level != (3,):
        raise ValueError("required isolated recovery durability is unavailable")


def create_isolated_restore_ledger(
    store: AXNodeStore, parent: str | Path, *, allow_isolated_write: bool = False,
) -> Path:
    """Create a new, exclusively owned recovery directory under a local parent."""
    _require_write_permission(allow_isolated_write)
    source_sha = _source_sha(store)
    parent = _private_directory(parent)
    if parent.is_relative_to(store.root):
        raise PermissionError("recovery directory cannot be inside the original store")
    _outside_axnode_store(parent)
    root = Path(tempfile.mkdtemp(prefix=_RECOVERY_DIR_PREFIX, dir=parent))
    path = root / _RECOVERY_DB
    os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    with closing(sqlite3.connect(path, timeout=3)) as db:
        _configure_database(db)
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(f"PRAGMA application_id={_APPLICATION_ID}")
            db.execute("PRAGMA user_version=1")
            for ddl in _SCHEMA.values():
                db.execute(ddl)
            db.execute("INSERT INTO source_binding VALUES (1, ?)", (source_sha,))
    return root


@contextmanager
def _recovery_transaction(root: Path, *, write: bool) -> Iterator[sqlite3.Connection]:
    path = _private_files(root)
    uri = path.as_uri() + "?mode=rw&cache=private"
    # Even a read can resolve a hot rollback journal. Permit that only in this
    # recognized, exclusively named recovery directory.
    with closing(sqlite3.connect(uri, uri=True, timeout=3)) as db, db:
        _configure_database(db)
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        schema = dict(db.execute("SELECT name, sql FROM sqlite_schema WHERE sql IS NOT NULL"))
        if schema != _SCHEMA:
            raise ValueError("unrecognized isolated recovery schema")
        if write:
            _limit_pages(db, _MAX_LEDGER_BYTES)
        yield db


def _limit_pages(db: sqlite3.Connection, byte_limit: int) -> None:
    pages = byte_limit // db.execute("PRAGMA page_size").fetchone()[0]
    actual_limit = db.execute(f"PRAGMA max_page_count={pages}").fetchone()[0]
    if actual_limit > pages:
        raise ValueError("isolated recovery storage budget exceeded")


def _read_log(db: sqlite3.Connection) -> list[_Transition]:
    rows = db.execute(
        "SELECT revision, operation_id, action, prior_epoch, epoch, "
        "checkpoint_sha256, payload_sha256 FROM transitions ORDER BY revision LIMIT ?",
        (_MAX_REVISIONS + 1,),
    ).fetchall()
    if len(rows) > _MAX_REVISIONS:
        raise ValueError("isolated recovery revision budget exceeded")
    log = [_Transition(*row) for row in rows]
    head = None
    for revision, row in enumerate(log, 1):
        if row.revision != revision or row.prior_epoch != head:
            raise ValueError("isolated recovery revision history is inconsistent")
        if row.action == "PUBLISH":
            if (row.epoch != revision
                    or not _valid_digest(row.checkpoint_sha256)
                    or not _valid_digest(row.payload_sha256)):
                raise ValueError("isolated recovery publication is inconsistent")
        elif row.action != "ROLLBACK" or head is None or row.epoch != log[head - 1].prior_epoch:
            raise ValueError("isolated recovery rollback is inconsistent")
        head = row.epoch
    return log


def _payload_sha(checkpoint: str, payload: IsolatedEpochPayload) -> str:
    if not 4 <= len(payload.files) <= _MAX_NODES + len(_DATABASE_FILES):
        raise ValueError("isolated epoch inventory exceeds budget")
    hashes = {}
    catalog_bytes = 0
    for name, content in payload.files:
        digest = hashlib.sha256(content).hexdigest()
        if name in hashes:
            raise ValueError("duplicate isolated epoch entry")
        if name in _DATABASE_FILES:
            if not _offline_sqlite_image(content):
                raise ValueError("invalid isolated recovery DB image")
        elif name != f"nodes/{digest}.axnode" or not 0 < len(content) <= MAX_NODE_BYTES:
            raise ValueError("invalid immutable node asset")
        if name not in ("memory.sqlite", "evidence.sqlite"):
            catalog_bytes += len(content)
        hashes[name] = digest
    if catalog_bytes > _MAX_ARCHIVE_BYTES or not set(_DATABASE_FILES) <= hashes.keys():
        raise ValueError("incomplete or oversized isolated epoch")
    return hashlib.sha256(canonical_bytes({
        "schema": "eai.axnode.isolated.write.epoch.v1",
        "read_checkpoint_sha256": checkpoint,
        "files": hashes,
    })).hexdigest()


def _load_payload(db: sqlite3.Connection, publication: _Transition) -> IsolatedEpochPayload:
    count, size = db.execute(
        "SELECT count(*), sum(length(content)) FROM epoch_files WHERE revision = ?",
        (publication.revision,),
    ).fetchone()
    if not 4 <= count <= _MAX_NODES + len(_DATABASE_FILES) or size > _MAX_PAYLOAD_BYTES:
        raise ValueError("incomplete or oversized isolated epoch")
    rows = db.execute(
        "SELECT name, content FROM epoch_files WHERE revision = ? ORDER BY name",
        (publication.revision,),
    ).fetchall()
    if any(type(name) is not str or type(content) is not bytes for name, content in rows):
        raise ValueError("invalid isolated epoch file types")
    payload = IsolatedEpochPayload(tuple(rows))
    if _payload_sha(publication.checkpoint_sha256, payload) != publication.payload_sha256:
        raise ValueError("isolated epoch payload integrity mismatch")
    return payload


def _check_operation(operation_id: str, expected_revision: int) -> None:
    if (type(operation_id) is not str or not _OPERATION_ID.fullmatch(operation_id)
            or type(expected_revision) is not int or not 0 <= expected_revision <= _MAX_REVISIONS):
        raise ValueError("invalid isolated recovery operation or revision")


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _replay_or_check_revision(
    log: list[_Transition], operation_id: str, expected_revision: int,
    action: str, checkpoint: str | None = None,
) -> _Transition | None:
    for record in log:
        if record.operation_id == operation_id:
            if (record.action != action or record.revision != expected_revision + 1
                    or record.checkpoint_sha256 != checkpoint):
                raise ValueError("isolated recovery operation ID already binds a different request")
            return record
    if len(log) != expected_revision:
        raise ValueError("isolated recovery revision changed")
    if len(log) == _MAX_REVISIONS:
        raise ValueError("isolated recovery revision budget exceeded")
    return None


def _append_transition(
    db: sqlite3.Connection, transition: _Transition, payload: IsolatedEpochPayload | None = None,
) -> None:
    db.execute("INSERT INTO transitions VALUES (?, ?, ?, ?, ?, ?, ?)", (
        transition.revision, transition.operation_id, transition.action,
        transition.prior_epoch, transition.epoch, transition.checkpoint_sha256,
        transition.payload_sha256,
    ))
    if payload is not None:
        db.executemany(
            "INSERT INTO epoch_files VALUES (?, ?, ?)",
            ((transition.revision, name, content) for name, content in payload.files),
        )


def _reserve_rollback_room(
    db: sqlite3.Connection, log: list[_Transition], prior: int | None,
) -> None:
    # Every selected epoch must still have a distinct revision for its undo.
    rollback_steps = 1
    while prior is not None:
        rollback_steps += 1
        prior = log[prior - 1].prior_epoch
    if len(log) + 1 + rollback_steps > _MAX_REVISIONS:
        raise ValueError("isolated recovery revision budget must reserve rollback")
    _limit_pages(db, _MAX_LEDGER_BYTES - _ROLLBACK_RESERVE_BYTES)


def _receipt(record: _Transition, log: list[_Transition]) -> IsolatedRestoreReceipt:
    selected = log[record.epoch - 1] if record.epoch is not None else None
    status = ("ISOLATED_RESTORE_PUBLISHED" if record.action == "PUBLISH"
              else "ISOLATED_RESTORE_ROLLED_BACK")
    return IsolatedRestoreReceipt(
        status, record.revision, record.epoch,
        selected.checkpoint_sha256 if selected else None,
        selected.payload_sha256 if selected else None,
    )


def commit_isolated_restore(
    store: AXNodeStore, archive: str | Path, isolated_root: str | Path,
    request: IsolatedRestoreRequest,
) -> IsolatedRestoreReceipt:
    """Commit a reviewed snapshot and select it in the same SQLite transaction.

    The operation ID binds the expected revision and reviewed checkpoint. A
    replay returns its historical receipt before re-reading the staged data.
    """
    if type(request) is not IsolatedRestoreRequest:
        raise ValueError("explicit isolated restore request required")
    _require_write_permission(request.allow_isolated_write)
    _check_operation(request.operation_id, request.expected_revision)
    checkpoint = request.reviewed_checkpoint_sha256
    if not _valid_digest(checkpoint):
        raise ValueError("reviewed isolated epoch checkpoint required")
    source_sha = _source_sha(store)
    root = _private_directory(request.recovery_root)
    if root.is_relative_to(store.root) or store.root.is_relative_to(root):
        raise PermissionError("recovery directory must be separate from the original store")
    with _recovery_transaction(root, write=True) as db:
        if db.execute("SELECT source_sha256 FROM source_binding").fetchall() != [(source_sha,)]:
            raise PermissionError("recovery ledger belongs to a different source store")
        log = _read_log(db)
        record = _replay_or_check_revision(
            log, request.operation_id, request.expected_revision, "PUBLISH", checkpoint,
        )
        if record is None:
            prior = log[-1].epoch if log else None
            _reserve_rollback_room(db, log, prior)
            if prior is not None:
                _load_payload(db, log[prior - 1])
            payload = capture_isolated_write_epoch(
                store, archive, isolated_root, checkpoint_sha256=checkpoint,
            )
            revision = len(log) + 1
            record = _Transition(revision, request.operation_id, "PUBLISH", prior,
                                 revision, checkpoint, _payload_sha(checkpoint, payload))
            _append_transition(db, record, payload)
            log.append(record)
        return _receipt(record, log)


def recover_isolated_restore(recovery_root: str | Path) -> IsolatedRestoreState:
    """Reopen a complete committed epoch without source or staged files."""
    with _recovery_transaction(_private_directory(recovery_root), write=False) as db:
        log = _read_log(db)
        head = log[-1].epoch if log else None
        if head is None:
            return IsolatedRestoreState(len(log), None, None, None, None)
        current = log[head - 1]
        return IsolatedRestoreState(
            len(log), head, current.checkpoint_sha256, current.payload_sha256,
            _load_payload(db, current),
        )


def rollback_isolated_restore(
    recovery_root: str | Path, *, operation_id: str, expected_revision: int,
    allow_isolated_write: bool = False,
) -> IsolatedRestoreReceipt:
    """Restore the previous isolated selection, retaining immutable history."""
    _require_write_permission(allow_isolated_write)
    _check_operation(operation_id, expected_revision)
    with _recovery_transaction(_private_directory(recovery_root), write=True) as db:
        log = _read_log(db)
        record = _replay_or_check_revision(log, operation_id, expected_revision, "ROLLBACK")
        if record is None:
            head = log[-1].epoch if log else None
            if head is None:
                raise ValueError("no published isolated restore to roll back")
            prior = log[head - 1].prior_epoch
            if prior is not None:
                _load_payload(db, log[prior - 1])
            record = _Transition(len(log) + 1, operation_id, "ROLLBACK", head, prior)
            _append_transition(db, record)
        return _receipt(record, log)
