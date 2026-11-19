"""C05 checkpoint checks and capture of audited AXNODE recovery payloads."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3

from .axnode_store import AXNodeStore
from .axnode_epoch import (
    IsolatedEpochPayload, ReadCheckpointUnavailable, _copy_checkpoint_database,
    shared_read_checkpoint,
)
from .contracts import canonical_bytes, strict_json
from .axnode_sidecar_backup import _COMPLETE_MARKER, _FILES, _MAX_DB, _MAX_ZIP
from .sidecar_recovery_audit import audit_isolated_sidecar_restore


@dataclass(frozen=True)
class CoherenceReview:
    disposition: str
    sidecar_count: int
    anchor_count: int
    source_node_count: int
    same_transaction_epoch_proven: bool = False
    may_bind_to_live_store: bool = False
    source_data_modified: bool = False
    source_sidecar_drift_detected: bool = False


def _row_fingerprint(path: Path, table: str, *, immutable: bool = False) -> str | None:
    if path.is_symlink():
        raise ValueError("symlinked source or restored sidecar")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > _MAX_DB:
        raise ValueError("invalid sidecar for coherence check")
    mode = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    with closing(sqlite3.connect(path.resolve(strict=True).as_uri() + mode,
                                 uri=True, timeout=3)) as db:
        return _fingerprint_rows(db, table)


def _fingerprint_rows(db: sqlite3.Connection, table: str) -> str:
    """Read-only full schema, payload and indexed metadata audit of one sidecar.

    A valid content hash alone is insufficient: an attacker could alter the
    un-hashed SQLite tier/anchor/polarity columns to poison recovery claims.
    All payloads remain on device and only opaque row digests are returned.
    """
    if table not in ("entries", "observations"):
        raise ValueError("unrecognized sidecar table")
    expected = {
        "entries": ("sha256", "anchor_sha", "tier", "label",
                    "captured_at", "payload"),
        "observations": ("sha256", "claim_id", "source_sha256",
                         "polarity", "observed_at", "expires_at", "payload"),
    }[table]
    digest = hashlib.sha256()
    if db.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise ValueError("unexpected sidecar user version")
    columns = {row[1] for row in db.execute('PRAGMA table_info("' + table + '")')}
    if columns != set(expected):
        raise ValueError("unrecognized source sidecar schema")
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("corrupt source sidecar")
    rows = db.execute(
        'SELECT ' + ",".join(expected) + ' FROM "' + table +
        '" ORDER BY sha256 LIMIT 3001'
    ).fetchall()
    if len(rows) > 3000:
        raise ValueError("coherence row budget exceeded")
    for row in rows:
        sha, *rest = row
        blob = rest[-1]
        if (type(sha) is not str or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)
                or type(blob) is not bytes or len(blob) > 2048
                or hashlib.sha256(blob).hexdigest() != sha):
            raise ValueError("sidecar index/payload hash mismatch")
        raw = strict_json(blob, max_bytes=2048)
        if type(raw) is not dict or canonical_bytes(raw) != blob:
            raise ValueError("noncanonical source sidecar payload")
        if table == "entries":
            metadata: tuple[object, ...] = (raw.get("anchor_sha"), raw.get("tier"),
                        raw.get("label"), raw.get("captured_at"))
            if raw.get("provenance") != "LOCAL_OBSERVATION_UNVERIFIED":
                raise ValueError("untrusted source memory provenance")
        else:
            metadata = (raw.get("claim_id"), raw.get("source_sha256"),
                        raw.get("polarity"), raw.get("observed_at"),
                        raw.get("expires_at"))
            if raw.get("origin") != "LOCAL_UNTRUSTED_OBSERVATION":
                raise ValueError("untrusted source evidence provenance")
        if tuple(rest[:-1]) != metadata:
            raise ValueError("source sidecar indexed metadata mismatch")
        digest.update(bytes.fromhex(sha))
    return digest.hexdigest()


def _source_fingerprints(store: AXNodeStore) -> tuple[str | None, ...]:
    return tuple(
        _row_fingerprint(store.root / original, table)
        for _restored, (original, table, _columns) in _FILES.items()
    )


def _isolated_fingerprints(root: Path) -> tuple[str | None, ...]:
    return tuple(
        _row_fingerprint(root / restored, table, immutable=True)
        for restored, (_original, table, _columns) in _FILES.items()
    )


def review_isolated_cross_db_coherence(
    store: AXNodeStore, archive: str | Path, isolated_root: str | Path,
) -> CoherenceReview:
    if type(store) is not AXNodeStore:
        raise ValueError("explicit source store required")
    before = tuple(store.hashes())
    source_before = _source_fingerprints(store)
    integrity = store.audit()
    if (integrity["sqlite_integrity"] != "ok"
            or integrity["foreign_key_violations"] != 0
            or integrity["invalid_hashes"] or integrity["orphan_files"]):
        raise ValueError("source AXNODE integrity not established")
    audited = audit_isolated_sidecar_restore(store, archive, isolated_root)
    after = tuple(store.hashes())
    source_after = _source_fingerprints(store)
    isolated = _isolated_fingerprints(Path(isolated_root).expanduser())
    if after != before:
        raise ValueError("source AXNODE graph changed during restore audit")
    drift = source_before != source_after or source_after != isolated
    if source_before != source_after:
        disposition = "HOLD_SOURCE_CHANGED_DURING_AUDIT"
    elif drift:
        disposition = "HOLD_SOURCE_SIDECAR_DRIFT"
    elif audited.archived_file_count != 2:
        disposition = "HOLD_MISSING_SIDE_CAR_COHERENCE"
    elif not audited.validated_row_count:
        disposition = "HOLD_EMPTY_RESTORE_HAS_NO_PROVENANCE"
    else:
        disposition = "HOLD_CROSS_DB_TRANSACTION_EPOCH_UNPROVEN"
    return CoherenceReview(disposition, audited.archived_file_count,
                           audited.matched_anchor_count, len(before),
                           source_sidecar_drift_detected=drift)


@dataclass(frozen=True)
class EpochConsistencyBoundary:
    status: str
    catalog_node_count: int
    source_sidecars: tuple[str | None, ...]
    isolated_sidecars: tuple[str | None, ...]
    sidecars_agree: bool
    transaction_epoch_proven: bool = False
    may_publish_restore: bool = False
    may_bind_active_store: bool = False
    original_modified: bool = False
    shared_read_checkpoint_sha256: str | None = None


def _catalog_rows(store: AXNodeStore) -> tuple[list[tuple], list[tuple]]:
    rows = store.db.execute(
        "SELECT sha256,node_id,version,status,kind,output_type,search_text "
        "FROM main.nodes ORDER BY sha256 LIMIT 3001"
    ).fetchall()
    edges = store.db.execute(
        "SELECT child_sha,parent_sha FROM main.parents ORDER BY child_sha,parent_sha "
        "LIMIT 36001"
    ).fetchall()
    if len(rows) > 3000 or len(edges) > 36000:
        raise ValueError("catalog checkpoint budget exceeded")
    audit = store.audit()
    if (audit["sqlite_integrity"] != "ok" or audit["foreign_key_violations"]
            or audit["invalid_hashes"] or audit["orphan_files"]):
        raise ValueError("source AXNODE integrity not established")
    return rows, edges


def _capture_epoch_payload(
    store: AXNodeStore, sidecars: tuple[sqlite3.Connection, ...],
    rows: list[tuple], edges: list[tuple],
) -> IsolatedEpochPayload:
    assets = []
    expected_edges: list[tuple[str, str]] = []
    for digest, *metadata in rows:
        node = store.get(digest)
        raw = node.as_dict()
        expected = (
            raw["id"], raw["version"], raw["status"], raw["kind"],
            raw["signature"]["output"], store._keywords(raw),
        )
        if tuple(metadata) != expected:
            raise ValueError("catalog metadata differs from immutable AXNODE")
        expected_edges.extend((digest, parent) for parent in raw["parent_hashes"])
        assets.append((f"nodes/{digest}.axnode", node.canonical))
    if sorted(expected_edges) != edges:
        raise ValueError("catalog parent graph differs from immutable AXNODE")
    catalog_image = _copy_checkpoint_database(store.db, {"nodes", "parents"})
    images = [(name, _copy_checkpoint_database(db, {table}))
              for db, (name, (_, table, _)) in zip(sidecars, _FILES.items(), strict=True)]
    return IsolatedEpochPayload((("catalog.sqlite", catalog_image), *images, *assets))


def _restore_stamp(bundle: Path, root: Path) -> tuple[tuple[int, ...], ...]:
    paths = (bundle, root, root / _COMPLETE_MARKER, *(root / name for name in _FILES))
    stamps: list[tuple[int, ...]] = []
    for path in paths:
        try:
            info = path.lstat()
        except FileNotFoundError:
            stamps.append(())
        else:
            stamps.append((info.st_dev, info.st_ino, info.st_size, info.st_mode,
                           info.st_mtime_ns, info.st_ctime_ns))
    return tuple(stamps)


def inspect_isolated_epoch_boundary(
    store: AXNodeStore, archive: str | Path, isolated_root: str | Path,
) -> EpochConsistencyBoundary:
    """Match an isolated restore to one stable read of the three source DBs.

    The checkpoint describes the observed contents. It carries no historical
    write-transaction proof or permission to publish a restore.
    """
    boundary, _ = _observe_epoch_boundary(store, archive, isolated_root)
    return boundary


def capture_isolated_write_epoch(
    store: AXNodeStore, archive: str | Path, isolated_root: str | Path, *,
    checkpoint_sha256: str,
) -> IsolatedEpochPayload:
    """Capture full payload from the same pinned view used for the audit."""
    boundary, payload = _observe_epoch_boundary(
        store, archive, isolated_root, capture_checkpoint=checkpoint_sha256,
    )
    if not boundary.sidecars_agree:
        raise ValueError(boundary.status)
    if payload is None:
        raise ValueError("isolated restore checkpoint differs from the reviewed checkpoint")
    return payload


def _observe_epoch_boundary(
    store: AXNodeStore, archive: str | Path, isolated_root: str | Path, *,
    capture_checkpoint: str | None = None,
) -> tuple[EpochConsistencyBoundary, IsolatedEpochPayload | None]:
    if type(store) is not AXNodeStore:
        raise ValueError("explicit local store required")
    bundle, root = Path(archive).expanduser(), Path(isolated_root).expanduser()
    sources = [store.root / source for source, _, _ in _FILES.values()]
    if any(path.is_symlink() for path in sources):
        raise ValueError("symlinked source sidecar")
    if not all(path.is_file() for path in sources):
        return EpochConsistencyBoundary("HOLD_MISSING_SOURCE_SIDECAR", 0, (), (), False), None
    if any(path.stat().st_size > _MAX_DB for path in (*sources, store.db_path)):
        raise ValueError("source database checkpoint budget exceeded")
    stamp = _restore_stamp(bundle, root)
    payload = None
    try:
        with shared_read_checkpoint(store, tuple(sources)) as readers:
            rows, edges = _catalog_rows(store)
            node_count = len(rows)
            catalog_sha = hashlib.sha256(canonical_bytes({
                "nodes": rows, "parents": edges,
            })).hexdigest()
            source = tuple(_fingerprint_rows(db, table) for db, (_, table, _) in
                           zip(readers, _FILES.values(), strict=True))
            audit = audit_isolated_sidecar_restore(store, bundle, root)
            restored = _isolated_fingerprints(root)
            # The isolated audit already validates contents and caps size.
            with bundle.open("rb") as handle:
                archive_bytes = handle.read(_MAX_ZIP + 1)
            if len(archive_bytes) > _MAX_ZIP:
                raise ValueError("checkpoint archive budget exceeded")
            checkpoint = hashlib.sha256(canonical_bytes({
                "schema": "eai.axnode.shared.read.checkpoint.v1",
                "catalog_sha256": catalog_sha,
                "sidecars": dict(zip(_FILES, source, strict=True)),
                "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
            })).hexdigest()
            complete = (source == restored and audit.archived_file_count == len(_FILES)
                        and audit.validated_row_count > 0)
            if complete and checkpoint == capture_checkpoint:
                payload = _capture_epoch_payload(store, readers, rows, edges)
    except ReadCheckpointUnavailable:
        return EpochConsistencyBoundary("HOLD_SOURCE_CHECKPOINT_UNAVAILABLE", 0, (), (), False), None
    if _restore_stamp(bundle, root) != stamp:
        return EpochConsistencyBoundary("HOLD_ISOLATED_RESTORE_CHANGED", node_count,
                                        source, restored, False), None
    if source != restored or audit.archived_file_count != len(_FILES):
        return EpochConsistencyBoundary("HOLD_MISMATCHED_ISOLATED_EPOCH", node_count,
                                        source, restored, False), None
    if not audit.validated_row_count:
        return EpochConsistencyBoundary("HOLD_EMPTY_RESTORE_HAS_NO_PROVENANCE", node_count,
                                        source, restored, False), None
    return EpochConsistencyBoundary("SHARED_READ_CHECKPOINT_MATCH", node_count,
                                    source, restored, True,
                                    shared_read_checkpoint_sha256=checkpoint), payload
