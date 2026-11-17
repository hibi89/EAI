"""C05 fail-closed, read-only cross-DB isolated restore boundary.

A correct SQLite backup of each sidecar and valid AXNODE anchors do NOT prove
they were captured at a common transaction epoch. No live attachment, import,
migration or user-data modification is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3

from .axnode_store import AXNodeStore
from .axnode_sidecar_backup import _FILES
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


def _row_fingerprint(path: Path, table: str) -> str | None:
    """Opaque, bounded read-only row fingerprint: never export row payloads."""
    if path.is_symlink():
        raise ValueError("symlinked source or restored sidecar")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("invalid sidecar for coherence check")
    digest = hashlib.sha256()
    with closing(sqlite3.connect(
            path.resolve(strict=True).as_uri() + "?mode=ro",
            uri=True, timeout=3)) as db:
        rows = db.execute(
            'SELECT sha256,payload FROM "' + table + '" ORDER BY sha256'
        ).fetchall()
    if len(rows) > 3000:
        raise ValueError("coherence row budget exceeded")
    for sha, blob in rows:
        if (type(sha) is not str or len(sha) != 64 or
                any(c not in "0123456789abcdef" for c in sha)
                or type(blob) is not bytes or len(blob) > 2048):
            raise ValueError("untrusted sidecar fingerprint inputs")
        if hashlib.sha256(blob).hexdigest() != sha:
            raise ValueError("sidecar index/payload hash mismatch")
        digest.update(bytes.fromhex(sha))
    return digest.hexdigest()


def _source_fingerprints(store: AXNodeStore) -> tuple[str | None, ...]:
    return tuple(
        _row_fingerprint(store.root / original, table)
        for _restored, (original, table, _columns) in _FILES.items()
    )


def _isolated_fingerprints(root: Path) -> tuple[str | None, ...]:
    return tuple(
        _row_fingerprint(root / restored, table)
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
