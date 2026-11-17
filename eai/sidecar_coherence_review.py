"""C05 fail-closed, read-only cross-DB isolated restore boundary.

A correct SQLite backup of each sidecar and valid AXNODE anchors do NOT prove
they were captured at a common transaction epoch. No live attachment, import,
migration or user-data modification is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .axnode_store import AXNodeStore
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


def review_isolated_cross_db_coherence(
    store: AXNodeStore, archive: str | Path, isolated_root: str | Path,
) -> CoherenceReview:
    if type(store) is not AXNodeStore:
        raise ValueError("explicit source store required")
    before = tuple(store.hashes())
    integrity = store.audit()
    if (integrity["sqlite_integrity"] != "ok"
            or integrity["foreign_key_violations"] != 0
            or integrity["invalid_hashes"] or integrity["orphan_files"]):
        raise ValueError("source AXNODE integrity not established")
    audited = audit_isolated_sidecar_restore(store, archive, isolated_root)
    after = tuple(store.hashes())
    if after != before:
        raise ValueError("source AXNODE graph changed during restore audit")
    if audited.archived_file_count != 2:
        disposition = "HOLD_MISSING_SIDE_CAR_COHERENCE"
    elif not audited.validated_row_count:
        disposition = "HOLD_EMPTY_RESTORE_HAS_NO_PROVENANCE"
    else:
        disposition = "HOLD_CROSS_DB_TRANSACTION_EPOCH_UNPROVEN"
    return CoherenceReview(disposition, audited.archived_file_count,
                           audited.matched_anchor_count, len(before))
