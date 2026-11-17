"""Common AXNODE read checkpoint and self-contained isolated SQLite images."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import stat

from .axnode_store import AXNodeStore
from .axnode_sidecar_backup import _MAX_DB


class ReadCheckpointUnavailable(ValueError):
    """The source could not be observed at a common read checkpoint."""


_SQLITE_OFFLINE_HEADER = b"\x01\x01"
_DATABASE_FILES = ("catalog.sqlite", "memory.sqlite", "evidence.sqlite")


@dataclass(frozen=True)
class IsolatedEpochPayload:
    """All bytes of one restorable catalog, sidecar pair and node inventory."""

    files: tuple[tuple[str, bytes], ...]

    @contextmanager
    def open_database(self, name: str) -> Iterator[sqlite3.Connection]:
        """Use a snapshot without creating or attaching an on-disk store."""
        if name not in _DATABASE_FILES:
            raise ValueError("unknown isolated epoch database")
        with closing(sqlite3.connect(":memory:")) as reader:
            reader.deserialize(dict(self.files)[name])
            reader.execute("PRAGMA trusted_schema=OFF")
            reader.execute("PRAGMA temp_store=MEMORY")
            reader.execute("PRAGMA query_only=ON")
            reader.set_authorizer(_snapshot_authorizer)
            yield reader


def _offline_sqlite_image(data: bytes) -> bool:
    return (100 <= len(data) <= _MAX_DB and data[:16] == b"SQLite format 3\x00"
            and data[18:20] == _SQLITE_OFFLINE_HEADER)


def _snapshot_authorizer(action: int, name: str | None, value: str | None, *_: object) -> int:
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and name == "query_only" and value is not None:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _copy_checkpoint_database(
    source: sqlite3.Connection, tables: set[str],
) -> bytes:
    """Copy a pinned view, then normalize its private copy for offline reads."""
    schema = source.execute(
        "SELECT type, name FROM main.sqlite_schema WHERE sql IS NOT NULL"
    ).fetchall()
    if ({name for kind, name in schema if kind == "table"} != tables
            or any(kind not in ("table", "index") for kind, _ in schema)):
        raise ValueError("unexpected isolated epoch source schema")
    pages = source.execute("PRAGMA page_count").fetchone()[0]
    page_size = source.execute("PRAGMA page_size").fetchone()[0]
    if pages * page_size > _MAX_DB:
        raise ValueError("isolated epoch database exceeds size budget")
    with closing(sqlite3.connect(":memory:")) as snapshot:
        if not hasattr(snapshot, "serialize") or not hasattr(snapshot, "deserialize"):
            raise ValueError("isolated recovery requires SQLite serialization support")
        source.backup(snapshot)
        snapshot.execute("PRAGMA trusted_schema=OFF")
        snapshot.execute("PRAGMA temp_store=MEMORY")
        # A backup of a WAL source may still carry WAL header bytes. Rebuild
        # on the in-memory database so reopen never needs a WAL companion.
        snapshot.execute("VACUUM")
        data = snapshot.serialize()
    if not _offline_sqlite_image(data):
        raise ValueError("invalid isolated checkpoint database image")
    return data


def _file_identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("checkpoint requires regular, unlinked databases")
    return info.st_dev, info.st_ino


def _data_version(db: sqlite3.Connection) -> int:
    return db.execute("PRAGMA data_version").fetchone()[0]


def _check_readable_sidecar(path: Path) -> None:
    # SQLite mode=ro may still create WAL coordination files. Only open a
    # WAL source when its existing coordination files can be reused.
    with path.open("rb") as handle:
        header = handle.read(20)
    if header[:16] != b"SQLite format 3\x00" or header[18:20] not in (b"\x01\x01", b"\x02\x02"):
        raise ValueError("invalid sidecar database header")
    if header[18:20] == b"\x02\x02":
        for suffix in ("-wal", "-shm"):
            companion = path.with_name(path.name + suffix)
            try:
                _file_identity(companion)
                size = companion.stat().st_size
            except FileNotFoundError as exc:
                raise ReadCheckpointUnavailable("sidecar WAL coordination unavailable") from exc
            if size > _MAX_DB:
                raise ReadCheckpointUnavailable("sidecar WAL coordination exceeds budget")


@contextmanager
def shared_read_checkpoint(
    store: AXNodeStore, sidecars: tuple[Path, ...],
) -> Iterator[tuple[sqlite3.Connection, ...]]:
    """Pin the catalog and sidecar views, then detect commits across the read.

    All version baselines precede all snapshots. All final version reads
    follow release of the snapshots, so a WAL commit hidden inside a pinned
    read is still detected. Versions are compared on the same connection.
    """
    if store.db.in_transaction:
        raise ReadCheckpointUnavailable("caller already owns a catalog transaction")
    paths = (store.db_path, *sidecars)
    identities = tuple(_file_identity(path) for path in paths)
    if len(set(identities)) != len(paths):
        raise ValueError("checkpoint databases must be distinct")
    for path in sidecars:
        _check_readable_sidecar(path)
    with ExitStack() as readers:
        sidecar_dbs = tuple(readers.enter_context(closing(sqlite3.connect(
            path.as_uri() + "?mode=ro&cache=private", uri=True, timeout=1,
        ))) for path in sidecars)
        for db in sidecar_dbs:
            db.execute("PRAGMA query_only=ON")
        databases = (store.db, *sidecar_dbs)
        try:
            before = tuple(_data_version(db) for db in databases)
            with ExitStack() as transactions:
                for db in databases:
                    db.execute("BEGIN")
                    transactions.callback(db.rollback)
                    # BEGIN alone is deferred. Reading a table pins the view.
                    db.execute("SELECT count(*) FROM sqlite_schema").fetchone()
                yield sidecar_dbs
            after = tuple(_data_version(db) for db in databases)
        except sqlite3.OperationalError as exc:
            if (getattr(exc, "sqlite_errorcode", 0) & 0xff) not in (
                    sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise
            raise ReadCheckpointUnavailable("source database busy") from exc
        if before != after or tuple(_file_identity(path) for path in paths) != identities:
            raise ReadCheckpointUnavailable("source changed during checkpoint")
