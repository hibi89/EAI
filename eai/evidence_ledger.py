"""Untrusted, hash-pinned local evidence observations for the EAI architect.

An AXNODE hash proves file integrity, not truth. Nothing in this module can
create VERIFIED facts, grant tool authority, or execute proposed strategies.
The index is an independent private SQLite sidecar, never part of Git.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time


_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MAX_OBSERVATIONS = 3000
_MAX_BYTES = 1024
_STATES = frozenset({"SUPPORT", "REFUTE"})
_FIELDS = frozenset({"version", "claim_id", "source_sha256", "polarity", "observed_at", "expires_at", "origin"})


def _name(value: str) -> str:
    if type(value) is not str or not _NAME.fullmatch(value):
        raise ValueError("evidence claim must be an opaque public identifier")
    return value


def _sha(value: str) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("evidence reference must be SHA256")
    return value


def _canonical(raw: dict) -> bytes:
    if type(raw) is not dict or set(raw) != _FIELDS:
        raise ValueError("unknown evidence observation fields")
    if (type(raw["version"]) is not int or raw["version"] != 1 or
            type(raw["origin"]) is not str or
            raw["origin"] != "LOCAL_UNTRUSTED_OBSERVATION"):
        raise ValueError("evidence cannot assert verified provenance")
    _name(raw["claim_id"])
    _sha(raw["source_sha256"])
    if type(raw["polarity"]) is not str or raw["polarity"] not in _STATES:
        raise ValueError("invalid observation polarity")
    at, expiry = raw["observed_at"], raw["expires_at"]
    if (type(at) is not int or not 0 <= at <= 9_999_999_999 or
            type(expiry) is not int or not at < expiry <= 9_999_999_999 or
            expiry - at > 366 * 86400):
        raise ValueError("evidence requires bounded observation expiry")
    blob = json.dumps(raw, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(blob) > _MAX_BYTES:
        raise ValueError("evidence record too large")
    return blob


@dataclass(frozen=True)
class ClaimAssessment:
    claim_id: str
    state: str
    supporting_hashes: tuple[str, ...]
    refuting_hashes: tuple[str, ...]
    stale_hashes: tuple[str, ...]
    trust: str = "NO_INDEPENDENT_VERIFIER"


class EvidenceLedger:
    """Explicit local sidecar; preview uses read-only mode if one exists."""

    def __init__(self, store: object, *, create: bool = False,
                 append_existing: bool = False):
        if type(create) is not bool or type(append_existing) is not bool or (
                create and append_existing):
            raise ValueError("choose exactly one explicit ledger write mode")
        root = getattr(store, "root", None)
        if not isinstance(root, Path) or not callable(getattr(store, "get", None)):
            raise ValueError("explicit AXNODE store required")
        self.store = store
        self.path = root / "evidence_ledger.sqlite"
        if self.path.is_symlink():
            raise ValueError("symlinked evidence ledger is unsafe")
        if create:
            if self.path.exists():
                raise FileExistsError("evidence ledger creation cannot overwrite")
            # Exclusive creation protects original or concurrent evidence.
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            self.db = sqlite3.connect(self.path, timeout=3)
            try:
                self.db.execute("PRAGMA journal_mode=WAL")
                self.db.execute("PRAGMA user_version=1")
                self.db.execute("CREATE TABLE observations ("
                                "sha256 TEXT PRIMARY KEY, claim_id TEXT NOT NULL, "
                                "source_sha256 TEXT NOT NULL, polarity TEXT NOT NULL, "
                                "observed_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, "
                                "payload BLOB NOT NULL)")
                self.db.execute("CREATE INDEX claim_lookup ON observations(claim_id)")
                self.db.commit()
            except Exception:
                self.db.close()
                raise
        else:
            if not self.path.is_file():
                raise FileNotFoundError("no evidence sidecar; unknown remains unknown")
            if append_existing:
                # Explicit local append; never create or migrate an existing DB.
                uri = self.path.resolve(strict=True).as_uri() + "?mode=rw"
            else:
                uri = self.path.resolve(strict=True).as_uri() + "?mode=ro"
            self.db = sqlite3.connect(uri, uri=True, timeout=3)
            if not append_existing:
                self.db.execute("PRAGMA query_only=ON")
        try:
            if int(self.db.execute("PRAGMA user_version").fetchone()[0]) != 1:
                raise ValueError("unsupported evidence ledger version")
            cols = {row[1] for row in self.db.execute("PRAGMA table_info(observations)")}
            if cols != {"sha256", "claim_id", "source_sha256", "polarity", "observed_at", "expires_at", "payload"}:
                raise ValueError("untrusted evidence schema layout")
            if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("corrupted evidence ledger")
        except Exception:
            self.db.close()
            raise
        self.writable = create or append_existing

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "EvidenceLedger":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def append(self, *, claim_id: str, source_sha256: str, polarity: str,
               observed_at: int, expires_at: int, now: int | None = None) -> str:
        if not self.writable:
            raise PermissionError("evidence preview is read-only")
        clock = int(time.time()) if now is None else now
        if type(clock) is not int or clock < 0 or type(observed_at) is not int or observed_at > clock:
            raise ValueError("future or invalid observation clock")
        raw = {"version": 1, "claim_id": claim_id,
               "source_sha256": source_sha256, "polarity": polarity,
               "observed_at": observed_at, "expires_at": expires_at,
               "origin": "LOCAL_UNTRUSTED_OBSERVATION"}
        blob = _canonical(raw)
        self.store.get(source_sha256)  # intact local content, not truth certification
        digest = hashlib.sha256(blob).hexdigest()
        with self.db:
            count = self.db.execute("SELECT count(*) FROM observations").fetchone()[0]
            if count >= _MAX_OBSERVATIONS:
                if self.db.execute("SELECT 1 FROM observations WHERE sha256=?", (digest,)).fetchone():
                    return digest
                raise ValueError("bounded evidence ledger full")
            self.db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?)",
                            (digest, claim_id, source_sha256, polarity, observed_at,
                             expires_at, blob))
        return digest

    def assess(self, claim_id: str, *, now: int | None = None) -> ClaimAssessment:
        _name(claim_id)
        clock = int(time.time()) if now is None else now
        if type(clock) is not int or not 0 <= clock <= 9_999_999_999:
            raise ValueError("invalid assessment clock")
        rows = self.db.execute(
            "SELECT sha256,source_sha256,polarity,observed_at,expires_at,payload "
            "FROM observations WHERE claim_id=? ORDER BY sha256 LIMIT ?",
            (claim_id, _MAX_OBSERVATIONS+1)).fetchall()
        if len(rows) > _MAX_OBSERVATIONS:
            raise ValueError("bounded evidence scan exceeded")
        support, refute, stale = [], [], []
        for digest, source, polarity, observed, expiry, payload in rows:
            if (type(digest) is not str or not _HASH.fullmatch(digest) or
                    hashlib.sha256(payload).hexdigest() != digest):
                raise ValueError("evidence bytes have been altered")
            try:
                raw = json.loads(payload)
            except (ValueError, TypeError, UnicodeError) as exc:
                raise ValueError("invalid ledger record") from exc
            if (_canonical(raw) != payload or
                    (raw["claim_id"],raw["source_sha256"],raw["polarity"],
                     raw["observed_at"],raw["expires_at"]) !=
                    (claim_id,source,polarity,observed,expiry)):
                raise ValueError("evidence metadata tampered")
            self.store.get(source)
            if observed > clock or clock >= expiry:
                stale.append(digest)
            elif polarity == "SUPPORT":
                support.append(digest)
            else:
                refute.append(digest)
        if support and refute:
            state = "CONTRADICTED_UNVERIFIED"
        elif refute:
            state = "REFUTED_UNVERIFIED"
        elif support:
            state = "SUPPORTED_UNVERIFIED"
        elif stale:
            state = "STALE_UNVERIFIED"
        else:
            state = "UNKNOWN"
        return ClaimAssessment(claim_id,state,tuple(support),tuple(refute),tuple(stale))
