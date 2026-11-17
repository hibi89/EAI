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
from .contracts import canonical_bytes, strict_json
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
    """Read-only full schema, payload and indexed metadata audit of one sidecar.

    A valid content hash alone is insufficient: an attacker could alter the
    un-hashed SQLite tier/anchor/polarity columns to poison recovery claims.
    All payloads remain on device and only opaque row digests are returned.
    """
    if table not in ("entries", "observations"):
        raise ValueError("unrecognized sidecar table")
    if path.is_symlink():
        raise ValueError("symlinked source or restored sidecar")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("invalid sidecar for coherence check")
    expected = {
        "entries": ("sha256", "anchor_sha", "tier", "label",
                    "captured_at", "payload"),
        "observations": ("sha256", "claim_id", "source_sha256",
                         "polarity", "observed_at", "expires_at", "payload"),
    }[table]
    digest = hashlib.sha256()
    with closing(sqlite3.connect(
            path.resolve(strict=True).as_uri() + "?mode=ro",
            uri=True, timeout=3)) as db:
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("unexpected sidecar user version")
        columns = {row[1] for row in db.execute(
            'PRAGMA table_info("' + table + '")')}
        if columns != set(expected):
            raise ValueError("unrecognized source sidecar schema")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("corrupt source sidecar")
        rows = db.execute(
            'SELECT ' + ",".join(expected) + ' FROM "' + table +
            '" ORDER BY sha256'
        ).fetchmany(3001)
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
        if canonical_bytes(raw) != blob:
            raise ValueError("noncanonical source sidecar payload")
        if table == "entries":
            metadata = (raw.get("anchor_sha"), raw.get("tier"),
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


# EAI-SWU-007: independently compare source and isolated copies, never
# counterfeit a shared SQLite transaction epoch.
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


def inspect_isolated_epoch_boundary(
    store: AXNodeStore, archive: str | Path, isolated_root: str | Path,
) -> EpochConsistencyBoundary:
    """Perform actual read-only coherence audit and record stable fingerprints.

    Equality proves content agreement at two observations only; without a
    shared commit coordinator there is *no* cross-DB epoch attestation.
    """
    if type(store) is not AXNodeStore:
        raise ValueError("explicit local store required")
    prior_nodes = tuple(store.hashes())
    previous = _source_fingerprints(store)
    observed = review_isolated_cross_db_coherence(store, archive, isolated_root)
    after = _source_fingerprints(store)
    recovered = _isolated_fingerprints(Path(isolated_root).expanduser())
    if tuple(store.hashes()) != prior_nodes:
        raise ValueError("source catalog changed across epoch read")
    if previous != after:
        raise ValueError("source sidecars changed across epoch read")
    match = previous == recovered and observed.source_sidecar_drift_detected is False
    if observed.same_transaction_epoch_proven or observed.may_bind_to_live_store:
        raise PermissionError("read-only coherence review cannot establish commit")
    return EpochConsistencyBoundary(
        "SOURCE_COPY_MATCH_UNVERIFIED_EPOCH" if match else
        "HOLD_MISMATCHED_ISOLATED_EPOCH",
        len(prior_nodes), previous, recovered, match)
