"""C16 durable *review-only* replay fence on opaque SHA-256 fingerprints.

New isolated SQLite file with strict no-overwrite creation and a unique index.
This stores no prompts, customer data, training signals or executable authority.
A hash does not authenticate the source; all reviewed episodes remain UNVERIFIED.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3

from .episode_replay_dedup import EpisodeBatchReview

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MAX_ROWS = 4096


@dataclass(frozen=True)
class ReplayFenceReceipt:
    status: str
    candidate_sha256: str
    recorded_count: int
    grants_learning: bool = False
    grants_execution: bool = False


class EpisodeReplayFence:
    """Separate review index; read-only unless explicitly created/opened RW."""

    def __init__(self, path: str | Path, *, create: bool = False,
                 append_existing: bool = False) -> None:
        if type(create) is not bool or type(append_existing) is not bool or (
                create and append_existing):
            raise ValueError("choose one explicit replay journal write mode")
        path = Path(path).expanduser()
        if (path.is_symlink() or not path.parent.is_dir()
                or path.parent.is_symlink()
                or (path.exists() and (not path.is_file() or create))
                or (not path.exists() and not create)):
            raise ValueError("existing safe journal or exclusive creation required")
        self.path = path.resolve(strict=False)
        self.writable = create or append_existing
        if create:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        uri = self.path.as_uri() + ("?mode=rw" if self.writable else "?mode=ro")
        self.db = sqlite3.connect(uri, uri=True, timeout=3)
        try:
            if create:
                self.db.execute("PRAGMA journal_mode=WAL")
                self.db.execute(
                    "CREATE TABLE reviews ("
                    "fingerprint TEXT PRIMARY KEY,"
                    "candidate_sha256 TEXT NOT NULL)")
                self.db.execute("PRAGMA user_version=1")
                self.db.commit()
                os.chmod(self.path, 0o600)
            if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("unrecognized replay fence version")
            columns = {x[1] for x in self.db.execute("PRAGMA table_info(reviews)")}
            if columns != {"fingerprint", "candidate_sha256"}:
                raise ValueError("unexpected replay fence layout")
            if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("replay fence integrity failure")
            if self.db.execute("SELECT count(*) FROM reviews").fetchone()[0] > _MAX_ROWS:
                raise ValueError("replay fence budget exceeded")
            self.db.execute("PRAGMA busy_timeout=3000")
            if not self.writable:
                self.db.execute("PRAGMA query_only=ON")
        except Exception:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "EpisodeReplayFence":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def contains(self, fingerprint: str) -> bool:
        if type(fingerprint) is not str or not _HASH.fullmatch(fingerprint):
            raise ValueError("invalid replay fingerprint")
        return self.db.execute(
            "SELECT 1 FROM reviews WHERE fingerprint=?",
            (fingerprint,)).fetchone() is not None

    def record(self, review: EpisodeBatchReview) -> ReplayFenceReceipt:
        if not self.writable:
            raise PermissionError("review replay index is read-only")
        if type(review) is not EpisodeBatchReview:
            raise ValueError("explicit episode review required")
        if (review.status != "SYNTHETIC_EPISODE_MANUAL_REVIEW_ONLY"
                or review.reasons or review.rejected_memory_hashes
                or review.admits_training or review.grants_execution):
            raise ValueError("held or privileged episode review cannot be recorded")
        hashes = review.reviewed_fingerprints
        if (type(hashes) is not tuple or not 1 <= len(hashes) <= 32
                or len(set(hashes)) != len(hashes)
                or type(review.candidate_sha256) is not str
                or not _HASH.fullmatch(review.candidate_sha256)
                or any(type(h) is not str or not _HASH.fullmatch(h)
                       for h in hashes)):
            raise ValueError("invalid opaque review fingerprints")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if (self.db.execute("SELECT count(*) FROM reviews").fetchone()[0]
                    + len(hashes) > _MAX_ROWS):
                raise ValueError("replay fence limit exceeded")
            if any(self.contains(h) for h in hashes):
                raise ValueError("replayed experience already recorded")
            self.db.executemany(
                "INSERT INTO reviews(fingerprint,candidate_sha256) VALUES (?,?)",
                ((h, review.candidate_sha256) for h in hashes))
        return ReplayFenceReceipt(
            "REVIEW_FINGERPRINTS_RECORDED_UNVERIFIED",
            review.candidate_sha256, len(hashes))
