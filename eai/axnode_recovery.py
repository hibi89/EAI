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
