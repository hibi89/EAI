"""Small, transactionally bounded workstation journal. Never stores input text."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time

from .local_files import local_path


PAGES = ("home", "architect", "atlas", "player", "verifier", "history", "settings")
OPERATIONS = ("command", "example", "draft_open", "draft_save", "discover",
              "create_library", "import_candidate", "design", "catalog",
              "node", "plan", "simulate", "verify", "settings", "journey")
OUTCOMES = {
    "OK", "ERROR", "DENIED", "UNAVAILABLE", "INPUT_INVALID", "FILE_UNAVAILABLE",
    "LOCAL_STORE_ERROR", "LOCAL_OPERATION_FAILED", "HOLD_UNSUPPORTED_REQUEST",
    "HOLD_EXPLICIT_NOTE_APPROVAL", "HOLD_NOTE_NOT_APPROVED",
    "HOLD_NO_REMOTE_OR_LOCAL_SEARCH_CONFIGURED", "HOLD_POLICY_DENIED",
    "HOLD_PLAN_CHANGED", "HOLD_PURE_SIMULATION_CONFIRMATION", "DRAFT_OPENED",
    "DRAFT_SAVED", "EXAMPLE_READY", "CANDIDATES_UNVERIFIED", "PARTIAL_UNVERIFIED",
    "BLOCKED", "BLOCKED_EVIDENCE_DISPUTE", "CANCELLED", "LOCAL_CATALOG_UNVERIFIED",
    "NODE_DIGEST_MATCH", "PURE_SYNTHETIC_PREVIEW_ONLY", "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED",
    "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED", "LOCAL_JOURNEY_DIGEST_INTEGRITY_UNVERIFIED",
    "RECEIPT_DIGEST_MISMATCH", "RECEIPT_CONTRACT_REJECTED", "SETTINGS_SAVED",
    "TYPED_DOMAIN_MATCH_UNVERIFIED", "NO_TYPED_CPU_MATCH",
    "PRIVATE_EMPTY_LIBRARY_CREATED", "PRIVATE_CANDIDATE_IMPORTED_UNVERIFIED",
    "HOLD_PRIVATE_LIBRARY_CONSENT", "HOLD_PRIVATE_IMPORT_CONSENT",
    "TWO_PLANS_ADVISORY_UNVERIFIED", "HOLD_OWNER_REVIEW_REQUIRED",
    "HOLD_INCOMPLETE_PROBLEM", "HOLD_LOCAL_READ_NOT_APPROVED",
    "HOLD_LOCAL_LIBRARY_REQUIRED", "HOLD_DISTINCT_PLANS_NOT_ESTABLISHED",
}


@dataclass(frozen=True)
class WorkspaceLimits:
    steps: int = 8
    seconds: int = 60
    expansions: int = 8

    def __post_init__(self):
        for value, maximum in ((self.steps, 64), (self.seconds, 300), (self.expansions, 8)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid workspace budget")


def private_db(root: Path, name: str) -> Path:
    root = local_path(root, private=True)
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    for suffix in ("", "-wal", "-shm", "-journal"):
        local_path(str(path) + suffix, private=True)
    return path


class DesktopState:
    def __init__(self, root: Path):
        self.root = root

    @contextmanager
    def _connection(self):
        path = private_db(self.root, "workspace.sqlite3")
        with closing(sqlite3.connect(path, timeout=2)) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("CREATE TABLE IF NOT EXISTS events "
                       "(id INTEGER PRIMARY KEY, stamp INTEGER, page TEXT, op TEXT, status TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS limits "
                       "(id INTEGER PRIMARY KEY CHECK(id=1), steps INTEGER, seconds INTEGER, expansions INTEGER)")
            yield db

    def _exists(self) -> bool:
        return local_path(self.root / "workspace.sqlite3", private=True).is_file()

    def history(self) -> list[tuple]:
        if not self._exists():
            return []
        with self._connection() as db:
            rows = db.execute("SELECT stamp,page,op,status FROM events ORDER BY id DESC LIMIT 100").fetchall()
        if any(type(stamp) is not int or not 0 <= stamp <= 4102444800 or page not in PAGES or
               op not in OPERATIONS or status not in OUTCOMES for stamp, page, op, status in rows):
            raise ValueError("invalid private status journal")
        return rows

    def record(self, page: str, operation: str, status: str) -> None:
        if page not in PAGES or operation not in OPERATIONS or status not in OUTCOMES:
            raise ValueError("unknown journal metadata")
        with self._connection() as db, db:
            db.execute("INSERT INTO events(stamp,page,op,status) VALUES(?,?,?,?)",
                       (int(time.time()), page, operation, status))
            db.execute("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 100)")

    def limits(self) -> WorkspaceLimits:
        if not self._exists():
            return WorkspaceLimits()
        with self._connection() as db:
            row = db.execute("SELECT steps,seconds,expansions FROM limits WHERE id=1").fetchone()
        return WorkspaceLimits(*row) if row else WorkspaceLimits()

    def set_limits(self, limits: WorkspaceLimits) -> None:
        if type(limits) is not WorkspaceLimits:
            raise ValueError("typed workspace limits required")
        with self._connection() as db, db:
            db.execute("INSERT OR REPLACE INTO limits VALUES(1,?,?,?)",
                       (limits.steps, limits.seconds, limits.expansions))
