"""Small, transactionally bounded workstation journal. Never stores input text."""
from __future__ import annotations

from contextlib import closing, contextmanager
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time

from .local_files import local_path
from .contracts import ProblemSpec, canonical_bytes, strict_json


PAGES = ("home", "architect", "atlas", "player", "verifier", "history", "settings")
OPERATIONS = ("command", "example", "draft_open", "draft_save", "discover",
              "create_library", "import_candidate", "design", "catalog",
              "node", "plan", "simulate", "trace_review", "remember_trace",
              "session_save", "session_load", "verify", "settings", "journey")
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
    "HOLD_TRACE_UNVERIFIED", "HOLD_MEMORY_CONSENT",
    "PURE_REPLAY_INTEGRITY_UNVERIFIED_REALITY", "PRIVATE_TRACE_CANDIDATE_UNVERIFIED",
    "SESSION_SAVED_REVIEW_ONLY", "SESSION_RESTORED_REVIEW_REQUIRED",
    "HOLD_SESSION_SOURCE_MISSING", "HOLD_NO_SAVED_SESSION",
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
        # An existing journal is owner data, not a blank migration target.
        # Never silently recreate missing tables in a damaged or substituted
        # database. New-file initialization is atomic across worker threads.
        missing_before_open = not path.exists()
        with closing(sqlite3.connect(path, timeout=5)) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            with db:
                db.execute("BEGIN IMMEDIATE")
                objects = db.execute(
                    "SELECT type,name FROM sqlite_master "
                    "WHERE type IN ('table','view','trigger')").fetchall()
                if missing_before_open and not objects:
                    db.execute("CREATE TABLE events "
                               "(id INTEGER PRIMARY KEY, stamp INTEGER, page TEXT, op TEXT, status TEXT)")
                    db.execute("CREATE TABLE limits "
                               "(id INTEGER PRIMARY KEY CHECK(id=1), steps INTEGER, seconds INTEGER, expansions INTEGER)")
                    objects = db.execute(
                        "SELECT type,name FROM sqlite_master "
                        "WHERE type IN ('table','view','trigger')").fetchall()
                if set(objects) != {("table", "events"), ("table", "limits")}:
                    raise ValueError("unexpected workspace schema; preserve source")
                expected = {
                    "events": ("id", "stamp", "page", "op", "status"),
                    "limits": ("id", "steps", "seconds", "expansions"),
                }
                for table, columns in expected.items():
                    observed = tuple(row[1] for row in db.execute(
                        "PRAGMA table_info(" + table + ")"))
                    if observed != columns:
                        raise ValueError("unexpected workspace columns; preserve source")
                if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ValueError("workspace SQLite integrity failed; preserve source")
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

    @contextmanager
    def _session_connection(self):
        """Separate versioned owner-private ledger; no automatic old DB migration."""
        path = private_db(self.root, "review_sessions.sqlite3")
        existed = path.is_file() and path.stat().st_size > 0
        with closing(sqlite3.connect(path, timeout=2)) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA busy_timeout=2000")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if existed and version != 1:
                raise ValueError("unknown session schema version; preserve source")
            if not existed:
                with db:
                    db.execute("CREATE TABLE sessions(id INTEGER PRIMARY KEY, "
                               "stamp INTEGER NOT NULL, sha256 TEXT NOT NULL, "
                               "payload BLOB NOT NULL)")
                    db.execute("PRAGMA user_version=1")
            elif {r[1] for r in db.execute("PRAGMA table_info(sessions)")} != {
                    "id", "stamp", "sha256", "payload"}:
                raise ValueError("unexpected session schema; preserve source")
            yield db

    def _private_library(self, library):
        if library is None:
            return None
        selected = local_path(library, private=True)
        folder = local_path(self.root / "libraries", private=True)
        if (selected.parent != folder or not selected.name.startswith("library_")
                or selected.is_symlink()):
            return None  # An arbitrary old/customer library is never pinned for restart.
        return str(selected)

    def save_session(self, raw: dict, library=None, *, owner_approved=False, plan_sha256=None):
        if owner_approved is not True:
            return {"status": "HOLD_MEMORY_CONSENT", "saved": False}
        problem = ProblemSpec.validate(raw)
        if plan_sha256 is not None and (type(plan_sha256) is not str or not
                re.fullmatch(r"[0-9a-f]{64}", plan_sha256)):
            raise ValueError("invalid optional plan digest")
        record = {"version": 1, "draft": raw,
                  "private_library": self._private_library(library),
                  "last_plan_sha256": plan_sha256,
                  "execution_authorized": False,
                  "resume_requires_owner_review": True}
        payload = canonical_bytes(record)
        if len(payload) > 32768:
            raise ValueError("review session metadata too large")
        digest = hashlib.sha256(payload).hexdigest()
        with self._session_connection() as db, db:
            if db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= 100:
                raise ValueError("review session retention bound reached; no automatic deletion")
            cur = db.execute("INSERT INTO sessions(stamp,sha256,payload) VALUES(?,?,?)",
                             (int(time.time()), digest, payload))
            session_id = cur.lastrowid
        return {"status": "SESSION_SAVED_REVIEW_ONLY", "saved": True,
                "session_id": session_id, "problem_sha256": problem.digest(),
                "resume_requires_owner_review": True,
                "can_execute": False, "original_writes": 0, "external_actions": 0}

    def load_session(self, *, session_id=None):
        path = local_path(self.root / "review_sessions.sqlite3", private=True)
        if not path.is_file():
            return {"status": "HOLD_NO_SAVED_SESSION", "restored": False}
        with self._session_connection() as db:
            if session_id is None:
                row = db.execute("SELECT id,sha256,payload FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
            else:
                if type(session_id) is not int or not 1 <= session_id <= 2147483647:
                    raise ValueError("invalid session id")
                row = db.execute("SELECT id,sha256,payload FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return {"status": "HOLD_NO_SAVED_SESSION", "restored": False}
        ident, sha, payload = row
        if (type(payload) is not bytes or len(payload) > 32768 or
                type(sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", sha) or
                hashlib.sha256(payload).hexdigest() != sha):
            raise ValueError("session digest or size mismatch; do not trust content")
        record = strict_json(payload, max_bytes=32768)
        if (type(record) is not dict or set(record) != {
                "version", "draft", "private_library", "last_plan_sha256",
                "execution_authorized", "resume_requires_owner_review"} or
                record["version"] != 1 or record["execution_authorized"] is not False or
                record["resume_requires_owner_review"] is not True):
            raise ValueError("unknown or unsafe session content")
        raw = record["draft"]
        problem = ProblemSpec.validate(raw)
        folder_path = record["private_library"]
        valid_lib = None
        missing = False
        if folder_path is not None:
            if type(folder_path) is not str:
                raise ValueError("invalid saved library path")
            valid_lib = self._private_library(folder_path)
            if valid_lib is None or not Path(valid_lib).is_dir() or not (
                    Path(valid_lib) / "axnodes.sqlite").is_file():
                valid_lib, missing = None, True
        return {"status": "HOLD_SESSION_SOURCE_MISSING" if missing else
                        "SESSION_RESTORED_REVIEW_REQUIRED",
                "restored": True, "session_id": ident, "draft": raw,
                "library": Path(valid_lib) if valid_lib else None,
                "problem_sha256": problem.digest(), "last_plan_sha256": record["last_plan_sha256"],
                "review_required": True, "can_execute": False,
                "original_writes": 0, "external_actions": 0}

    def set_limits(self, limits: WorkspaceLimits) -> None:
        if type(limits) is not WorkspaceLimits:
            raise ValueError("typed workspace limits required")
        with self._connection() as db, db:
            db.execute("INSERT OR REPLACE INTO limits VALUES(1,?,?,?)",
                       (limits.steps, limits.seconds, limits.expansions))
