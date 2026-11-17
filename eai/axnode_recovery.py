"""Read-only recovery preflight for AXNODE catalog and separate memory sidecars.

The legacy ZIP v1 backs up only AXNODE catalog and node files. This module
makes exclusion of private experience/evidence SQLite explicit instead of
silently implying full recovery. Never repairs, renames or deletes user data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from contextlib import closing

from .axnode_store import AXNodeStore

_SIDECARS = (
    ("memory", "axnode_memory.sqlite", "entries",
     {"sha256", "anchor_sha", "tier", "label", "captured_at", "payload"}),
    ("evidence", "evidence_ledger.sqlite", "observations",
     {"sha256", "claim_id", "source_sha256", "polarity",
      "observed_at", "expires_at", "payload"}),
)


@dataclass(frozen=True)
class RecoveryPreflight:
    state: str
    catalog_indexed: int
    source_findings: tuple[str, ...]
    sidecars: tuple[tuple[str, str], ...]
    disposition: str = "REVIEW_ONLY_NOT_EXECUTED"


def inspect_recovery_preflight(store: AXNodeStore) -> RecoveryPreflight:
    """Describe potential recovery gaps before any real snapshot/restore."""
    if type(store) is not AXNodeStore:
        raise ValueError("explicit local AXNODE store required")
    audit = store.audit()  # content-addressed nodes and SQLite FK are checked
    findings = []
    if audit["sqlite_integrity"] != "ok":
        findings.append("CATALOG_INTEGRITY_FAILURE")
    if audit["foreign_key_violations"]:
        findings.append("CATALOG_FOREIGN_KEY_FAILURE")
    if audit["invalid_hashes"]:
        findings.append("ALTERED_OR_MISSING_AXNODE")
    if audit["orphan_files"]:
        findings.append("ORPHAN_OR_STAGING_DATA_REQUIRES_REVIEW")
    if audit["indexed"] > 3000:
        findings.append("CATALOG_BACKUP_BUDGET_EXCEEDED")
    sidecars = []
    for kind, filename, table, expected_cols in _SIDECARS:
        path = store.root / filename
        if path.is_symlink():
            state = "UNSAFE_SYMLINK"
        elif not path.exists():
            state = "NOT_PRESENT"
        elif not path.is_file():
            state = "NOT_A_REGULAR_FILE"
        elif path.stat().st_size > 64 * 1024 * 1024:
            state = "BOUNDED_REVIEW_REQUIRED"
        elif (path.parent / (filename + "-wal")).exists():
            # Opening with SQLite immutable=1 while WAL is live can miss data.
            state = "WAL_SNAPSHOT_REQUIRED"
        else:
            # Immutable read avoids creating -shm/-wal; this is advisory
            # structural validation only, not a backup or trust proof.
            uri = path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
            try:
                with closing(sqlite3.connect(uri, uri=True, timeout=1)) as db:
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                    cols = {r[1] for r in db.execute(
                        'PRAGMA table_info("' + table + '")')}
                    check = db.execute("PRAGMA quick_check(1)").fetchone()[0]
                state = ("LOCAL_SIDECAR_NOT_IN_V1_BACKUP"
                         if version == 1 and cols == expected_cols and check == "ok"
                         else "SIDECAR_FORMAT_OR_INTEGRITY_REVIEW_REQUIRED")
            except sqlite3.DatabaseError:
                state = "SIDECAR_FORMAT_OR_INTEGRITY_REVIEW_REQUIRED"
        sidecars.append((kind, state))
        if state not in ("NOT_PRESENT",):
            findings.append(kind.upper() + "_EXCLUDED_FROM_V1_ARCHIVE")
    status = "REVIEW_REQUIRED" if findings else "AXNODE_V1_ONLY_CANDIDATE_UNVERIFIED"
    return RecoveryPreflight(status, audit["indexed"], tuple(findings),
                             tuple(sidecars))


# EAI-SWU-006: existing sidecar snapshot -> isolated restore -> commit audit.
@dataclass(frozen=True)
class IsolatedSidecarSnapshotReceipt:
    status: str
    archived_file_count: int
    restored_row_count: int
    matched_anchor_count: int
    archive_name: str | None
    restored_name: str | None
    original_modified: bool = False
    live_restore_applied: bool = False
    independent_semantic_proof: bool = False


def snapshot_and_audit_sidecars(
    store: AXNodeStore, archive: str | Path, isolated_restore: str | Path, *,
    perform_isolated_copy: bool = False,
) -> IsolatedSidecarSnapshotReceipt:
    """Opt-in isolated copy; no automatic restore to live AXNODE or customer DB.

    Existing backup/restore already do exclusive publication, WAL-safe copy,
    marker fsync and local SQLite validation. This links their actual receipts.
    A failure leaves any staged evidence for independent review, not deletion.
    """
    from .axnode_sidecar_backup import (
        create_sidecar_bundle, restore_sidecar_bundle)
    from .sidecar_recovery_audit import audit_isolated_sidecar_restore
    if type(store) is not AXNodeStore or type(perform_isolated_copy) is not bool:
        raise ValueError("typed explicit AXNODE recovery inputs required")
    pre = inspect_recovery_preflight(store)
    permitted = {"NOT_PRESENT", "LOCAL_SIDECAR_NOT_IN_V1_BACKUP",
                 "WAL_SNAPSHOT_REQUIRED"}
    if (pre.catalog_indexed > 3000 or
            any(state not in permitted for _, state in pre.sidecars) or
            any(issue not in {
                "MEMORY_EXCLUDED_FROM_V1_ARCHIVE",
                "EVIDENCE_EXCLUDED_FROM_V1_ARCHIVE",
            } for issue in pre.source_findings)):
        return IsolatedSidecarSnapshotReceipt(
            "HOLD_SOURCE_INTEGRITY_OR_SCHEMA", 0, 0, 0, None, None)
    if not perform_isolated_copy:
        return IsolatedSidecarSnapshotReceipt(
            "HOLD_EXPLICIT_ISOLATED_COPY_REQUIRED", 0, 0, 0, None, None)
    archive = Path(archive).expanduser()
    target = Path(isolated_restore).expanduser()
    if (archive.is_symlink() or target.is_symlink()
            or archive.exists() or target.exists()
            or archive.resolve(strict=False).is_relative_to(store.root)
            or target.resolve(strict=False).is_relative_to(store.root)
            or target.resolve(strict=False).is_relative_to(archive.parent / archive.name)
            or not archive.parent.is_dir() or not target.parent.is_dir()
            or archive.parent.is_symlink() or target.parent.is_symlink()):
        raise ValueError("fresh, separate, local destination paths required")
    if not any(s != "NOT_PRESENT" for _, s in pre.sidecars):
        return IsolatedSidecarSnapshotReceipt(
            "HOLD_NO_SIDECARS_PRESENT", 0, 0, 0, None, None)
    written = create_sidecar_bundle(store, archive)
    restored = restore_sidecar_bundle(written, target)
    audited = audit_isolated_sidecar_restore(store, written, restored)
    if (audited.status != "ISOLATED_RESTORE_INTEGRITY_ONLY_UNVERIFIED"
            or audited.original_data_modified or audited.bound_into_live_store):
        raise ValueError("isolated restore audit was not safe")
    return IsolatedSidecarSnapshotReceipt(
        "ISOLATED_BACKUP_RESTORED_AUDITED_UNVERIFIED",
        audited.archived_file_count, audited.validated_row_count,
        audited.matched_anchor_count, written.name, restored.name)


# EAI-SWU-008: staged recovery publication/rollback is an advisory decision
# until an atomic cross-DB checkpoint and independent verifier exist.
@dataclass(frozen=True)
class IsolatedRestoreDisposition:
    status: str
    isolated_marker_present: bool
    sidecar_count: int
    reason_codes: tuple[str, ...]
    requires_manual_rollback: bool
    staged_data_deleted: bool = False
    originals_touched: bool = False
    can_commit_to_live: bool = False


def review_isolated_restore_commit_or_hold(
    store: AXNodeStore, archive: str | Path, isolated_root: str | Path,
) -> IsolatedRestoreDisposition:
    """Check the true completion marker and independent coherence result.

    Never deletes, renames or rolls back a user-selected restored directory.
    A failed review is a HOLD with manual rollback required, not auto-cleanup.
    """
    from .axnode_sidecar_backup import _COMPLETE_MARKER
    from .sidecar_recovery_audit import audit_isolated_sidecar_restore
    from .sidecar_coherence_review import inspect_isolated_epoch_boundary
    if type(store) is not AXNodeStore:
        raise ValueError("explicit original AXNODE store required")
    root = Path(isolated_root).expanduser()
    if (root.is_symlink() or not root.is_dir()
            or root.resolve(strict=True).is_relative_to(store.root)):
        raise ValueError("isolated restore outside original store required")
    marker = root / _COMPLETE_MARKER
    if marker.is_symlink() or not marker.is_file():
        return IsolatedRestoreDisposition(
            "HOLD_INCOMPLETE_ISOLATED_RESTORE", False, 0,
            ("COMPLETION_MARKER_MISSING",), True)
    inspected = audit_isolated_sidecar_restore(store, archive, root)
    epoch = inspect_isolated_epoch_boundary(store, archive, root)
    if inspected.bound_into_live_store or inspected.original_data_modified:
        raise PermissionError("restore tried to modify original or live data")
    if not epoch.sidecars_agree:
        return IsolatedRestoreDisposition(
            "HOLD_ISOLATED_RESTORE_DIVERGENCE", True,
            inspected.archived_file_count, ("SOURCE_COPY_MISMATCH",), True)
    return IsolatedRestoreDisposition(
        "HOLD_CROSS_DB_EPOCH_AND_OWNER_APPROVAL",
        True, inspected.archived_file_count,
        ("NO_SHARED_TRANSACTION_EPOCH",
         "INDEPENDENT_RESTORE_VALIDATION_NOT_RUN",
         "NO_LIVE_STORE_COMMIT_AUTHORIZATION"), False)
