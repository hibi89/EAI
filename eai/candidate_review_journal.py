"""C15 append-only candidate review/quarantine log, isolated from live AXNODE.

This is a local *review* journal, not an approval/ACTIVE catalog. It cannot
write AXNODE files or promote/execute anything; owner and independent verifier
authorization remains a separate unimplemented gate.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sqlite3

from .candidate_evidence_review import CandidateEvidenceReview
from .contracts import canonical_bytes

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_STATES = frozenset({"REVIEW_HOLD", "QUARANTINED", "WITHDRAWN_FROM_REVIEW"})


@dataclass(frozen=True)
class JournalEntry:
    sequence: int
    candidate_sha256: str
    evidence_sha256: str
    state: str
    previous_active_sha256: str | None
    previous_entry_sha256: str
    entry_sha256: str
    permits_promotion: bool = False
    changes_active_node: bool = False


def _digest(value: str) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("invalid journal hash")
    return value


def _entry_hash(seq: int, candidate: str, evidence: str, state: str,
                active: str | None, previous: str) -> str:
    return hashlib.sha256(canonical_bytes({
        "schema": "eai.candidate.review.entry.v1",
        "sequence": seq, "candidate_sha256": candidate,
        "evidence_sha256": evidence, "state": state,
        "previous_active_sha256": active,
        "previous_entry_sha256": previous,
    })).hexdigest()


class CandidateReviewJournal:
    """Separate new SQLite v1 sidecar. No existing DB migration or activation."""

    def __init__(self, path: str | Path, *, create: bool = False):
        path = Path(path).expanduser()
        if (path.is_symlink() or not path.parent.is_dir()
                or path.parent.is_symlink()
                or (path.exists() and (not path.is_file() or create))
                or (not path.exists() and not create)):
            raise ValueError("safe explicit review journal path required")
        self.path = path.resolve(strict=False)
        self.db = sqlite3.connect(self.path, timeout=3)
        try:
            self.db.execute("PRAGMA busy_timeout=3000")
            self.db.execute("PRAGMA journal_mode=WAL")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if create:
                if version != 0:
                    raise ValueError("journal already initialized")
                self.db.executescript("""
                    CREATE TABLE entries (
                        sequence INTEGER PRIMARY KEY,
                        candidate_sha256 TEXT NOT NULL,
                        evidence_sha256 TEXT NOT NULL,
                        state TEXT NOT NULL,
                        previous_active_sha256 TEXT,
                        previous_entry_sha256 TEXT NOT NULL,
                        entry_sha256 TEXT NOT NULL UNIQUE
                    );
                    PRAGMA user_version=1;
                """)
                self.db.commit()
                os.chmod(self.path, 0o600)
            elif version != 1:
                raise ValueError("unknown journal version")
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(entries)")}
            expected = {
                "sequence", "candidate_sha256", "evidence_sha256", "state",
                "previous_active_sha256", "previous_entry_sha256", "entry_sha256",
            }
            if columns != expected or self.db.execute(
                    "PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("unsafe journal schema/integrity")
            self.verify_chain()
        except Exception:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "CandidateReviewJournal":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(JournalEntry(*row) for row in self.db.execute(
            "SELECT sequence,candidate_sha256,evidence_sha256,state,"
            "previous_active_sha256,previous_entry_sha256,entry_sha256 "
            "FROM entries ORDER BY sequence"))

    def verify_chain(self) -> bool:
        previous = "0" * 64
        for index, item in enumerate(self.entries(), 1):
            if (item.sequence != index or item.previous_entry_sha256 != previous
                    or item.state not in _STATES
                    or (item.previous_active_sha256 is not None
                        and not _HASH.fullmatch(item.previous_active_sha256))
                    or _digest(item.candidate_sha256) != item.candidate_sha256
                    or _digest(item.evidence_sha256) != item.evidence_sha256
                    or item.entry_sha256 != _entry_hash(
                        index, item.candidate_sha256, item.evidence_sha256,
                        item.state, item.previous_active_sha256, previous)):
                raise ValueError("journal chain integrity failure")
            previous = item.entry_sha256
        return True

    def record(self, review: CandidateEvidenceReview, *,
               state: str, previous_active_sha256: str | None = None
               ) -> JournalEntry:
        if type(review) is not CandidateEvidenceReview:
            raise ValueError("explicit untrusted review required")
        if (review.permits_promotion or review.permits_learning
                or review.permits_real_execution):
            raise ValueError("untrusted promotion or learning authority denied")
        if type(state) is not str or state not in _STATES:
            raise ValueError("only non-active review states supported")
        _digest(review.candidate_sha256)
        _digest(review.review_sha256)
        _digest(review.problem_sha256)
        _digest(review.fixture_sha256)
        if previous_active_sha256 is not None:
            _digest(previous_active_sha256)
        # A user may note an existing ACTIVE pointer, but this module cannot
        # change it. The pointer is audit metadata, never an authorization.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.verify_chain()
            existing = self.entries()
            if len(existing) >= 10000:
                raise ValueError("bounded review journal full")
            if state == "WITHDRAWN_FROM_REVIEW" and not any(
                    e.candidate_sha256 == review.candidate_sha256
                    for e in existing):
                raise ValueError("candidate not previously reviewed")
            index = len(existing) + 1
            previous = existing[-1].entry_sha256 if existing else "0" * 64
            digest = _entry_hash(index, review.candidate_sha256,
                                 review.review_sha256, state,
                                 previous_active_sha256, previous)
            self.db.execute(
                "INSERT INTO entries VALUES(?,?,?,?,?,?,?)",
                (index, review.candidate_sha256, review.review_sha256,
                 state, previous_active_sha256, previous, digest))
        return JournalEntry(index, review.candidate_sha256, review.review_sha256,
                            state, previous_active_sha256, previous, digest)
