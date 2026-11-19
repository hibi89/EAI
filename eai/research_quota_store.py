"""EAI-SWU-036 SQLite durable local MOCK-only quota and fail-closed breaker.

New opt-in isolated ledger only. This is not a provider entitlement, HTTP
client, paid quota or authorization to transmit any request. No reset routine.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from time import time
from contextlib import closing
import sqlite3

from .research_quota import ResearchLimits

_VERSION = 1
_MAX_EVENTS = 3000


@dataclass(frozen=True)
class DurableMockQuotaDecision:
    allowed: bool
    reason: str
    request_index: int = 0
    remote_send_allowed: bool = False
    paid_access_enabled: bool = False


class DurableMockQuota:
    """SQLite IMMEDIATE transaction serializes cross-process mock reservations."""

    def __init__(self, path: str | Path, *,
                 limits: ResearchLimits | None = None,
                 allow_create: bool = False):
        if type(allow_create) is not bool:
            raise ValueError("explicit local file creation flag required")
        self.limits = ResearchLimits() if limits is None else limits
        if type(self.limits) is not ResearchLimits:
            raise ValueError("typed conservative local limits required")
        file = Path(path).expanduser()
        if (file.is_symlink() or not file.parent.is_dir()
                or file.parent.is_symlink()
                or (file.exists() and not file.is_file())
                or file.suffix != ".sqlite"):
            raise ValueError("explicit ordinary isolated SQLite ledger required")
        exists = file.exists()
        if not exists and not allow_create:
            raise FileNotFoundError("owner must explicitly create a new mock ledger")
        if not exists:
            # An exclusive private file claim prevents a race with customer or
            # another process data; never let sqlite mode=rwc open a surprise.
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(file, flags, 0o600)
            os.close(fd)
        self.path = file
        # Existing files are opened rw, never recreated or auto-migrated.
        uri = file.resolve(strict=True).as_uri() + "?mode=rw"
        self.db = sqlite3.connect(uri, uri=True, timeout=3, isolation_level=None)
        try:
            self.db.execute("PRAGMA busy_timeout=3000")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if exists:
                if version != _VERSION:
                    raise ValueError("unknown local mock ledger version")
                schema = {
                    row[0] for row in self.db.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                if schema != {"reservations", "breaker"}:
                    raise ValueError("unexpected local mock ledger schema")
            else:
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    self.db.execute(
                        "CREATE TABLE reservations("
                        "id INTEGER PRIMARY KEY, stamp INTEGER NOT NULL, "
                        "tokens INTEGER NOT NULL)")
                    self.db.execute(
                        "CREATE TABLE breaker("
                        "id INTEGER PRIMARY KEY CHECK(id=1), "
                        "state TEXT NOT NULL, reason TEXT NOT NULL)")
                    self.db.execute(
                        "INSERT INTO breaker VALUES(1,'OFFLINE_MOCK_ONLY','')")
                    self.db.execute("PRAGMA user_version=1")
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK")
                    raise
            if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("local mock ledger integrity failure")
            row = self.db.execute(
                "SELECT state,reason FROM breaker WHERE id=1").fetchone()
            if row is None or row[0] not in (
                    "OFFLINE_MOCK_ONLY", "HOLD_LOCAL_MOCK_FAILURE"):
                raise ValueError("unexpected mock breaker status")
        except BaseException:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "DurableMockQuota":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    @staticmethod
    def _epoch(now: int | None) -> int:
        stamp = int(time()) if now is None else now
        if type(stamp) is not int or not 0 <= stamp <= 9999999999:
            raise ValueError("invalid UTC epoch for durable mock quota")
        return stamp

    def reserve(self, input_tokens: int, output_cap_tokens: int, *,
                now: int | None = None) -> DurableMockQuotaDecision:
        if (type(input_tokens) is not int or type(output_cap_tokens) is not int
                or not 1 <= input_tokens <= self.limits.max_input_tokens
                or not 1 <= output_cap_tokens <= self.limits.max_output_tokens):
            return DurableMockQuotaDecision(False, "INVALID_TOKEN_BUDGET")
        stamp = self._epoch(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT state FROM breaker WHERE id=1").fetchone()
            if row != ("OFFLINE_MOCK_ONLY",):
                decision = DurableMockQuotaDecision(False, "PERSISTENT_MOCK_HOLD")
            else:
                count = self.db.execute(
                    "SELECT count(*) FROM reservations").fetchone()[0]
                if count >= _MAX_EVENTS:
                    decision = DurableMockQuotaDecision(False, "MOCK_LEDGER_CAP")
                else:
                    recent_day = self.db.execute(
                        "SELECT count(*) FROM reservations "
                        "WHERE stamp > ? AND stamp <= ?", (stamp-86400,stamp)
                    ).fetchone()[0]
                    minute = self.db.execute(
                        "SELECT count(*),coalesce(sum(tokens),0) "
                        "FROM reservations WHERE stamp > ? AND stamp <= ?",
                        (stamp-60,stamp)).fetchone()
                    if (recent_day >= self.limits.rpd_local
                            or minute[0] >= self.limits.rpm_local):
                        decision = DurableMockQuotaDecision(
                            False, "LOCAL_MOCK_REQUEST_LIMIT")
                    elif (minute[1] + input_tokens + output_cap_tokens
                          > self.limits.tpm_local):
                        decision = DurableMockQuotaDecision(
                            False, "LOCAL_MOCK_TOKEN_LIMIT")
                    else:
                        cur = self.db.execute(
                            "INSERT INTO reservations(stamp,tokens) VALUES(?,?)",
                            (stamp,input_tokens+output_cap_tokens))
                        if cur.lastrowid is None:
                            raise ValueError("reservation ID unavailable")
                        decision = DurableMockQuotaDecision(
                            True, "LOCAL_MOCK_RESERVED_ONLY", cur.lastrowid)
            self.db.execute("COMMIT")
            return decision
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def record_mock_failure(self, *, status_code: int,
                            now: int | None = None) -> str:
        """429/provider failures survive process restart; no auto-reset."""
        self._epoch(now)
        if type(status_code) is not int or status_code not in (429, 500, 503):
            raise ValueError("unsupported local synthetic failure code")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "UPDATE breaker SET state='HOLD_LOCAL_MOCK_FAILURE',reason=? "
                "WHERE id=1", (f"MOCK_{status_code}",))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return "HOLD_LOCAL_MOCK_FAILURE"
