"""Isolated AXNODE memory tiers: bounded local metadata, never raw prompts.

This is an unverified experience index, NOT independent verifier evidence,
automatic learning, node activation, or autonomous execution.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sqlite3
import time

from .axnode_store import AXNodeStore
from .contracts import canonical_bytes, strict_json

_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_TIERS = frozenset({"WORKING", "EPISODIC", "SEMANTIC", "PROCEDURAL", "NEGATIVE"})
_OUTCOMES = frozenset({"UNKNOWN", "SUCCESS_OBSERVED", "FAILURE_OBSERVED"})
_LIMIT = 3000


def _identifier(v: str) -> str:
    if type(v) is not str or not _ID.fullmatch(v):
        raise ValueError("memory fields must be bounded public identifiers")
    return v


class AXNodeMemory:
    """New SQLite ledger tied to an explicit AXNodeStore; no legacy DB writes."""

    def __init__(self, store: AXNodeStore):
        if type(store) is not AXNodeStore:
            raise ValueError("explicit AXNODE store required")
        self.store = store
        path = store.root / "axnode_memory.sqlite"
        if path.is_symlink():
            raise ValueError("memory DB symlink forbidden")
        exists = path.exists() and path.stat().st_size > 0
        self.db = sqlite3.connect(path, timeout=3)
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if exists and version != 1:
                raise ValueError("unknown memory DB version; no automatic migration")
            if not exists:
                self.db.execute("CREATE TABLE entries("
                                "sha256 TEXT PRIMARY KEY, anchor_sha TEXT NOT NULL,"
                                "tier TEXT NOT NULL, label TEXT NOT NULL,"
                                "captured_at INTEGER NOT NULL, payload BLOB NOT NULL)")
                self.db.execute("CREATE INDEX entries_anchor ON entries(anchor_sha)")
                self.db.execute("PRAGMA user_version=1")
                self.db.commit()
            elif {r[1] for r in self.db.execute("PRAGMA table_info(entries)")} != {
                    "sha256", "anchor_sha", "tier", "label", "captured_at", "payload"}:
                raise ValueError("memory schema mismatch")
        except Exception:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "AXNodeMemory":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @staticmethod
    def _validate(raw: dict) -> bytes:
        if type(raw) is not dict or set(raw) != {
                "version", "tier", "anchor_sha", "label", "tags",
                "outcome", "captured_at", "ttl_seconds", "provenance"}:
            raise ValueError("invalid memory metadata fields")
        if type(raw["version"]) is not int or raw["version"] != 1:
            raise ValueError("unsupported memory version")
        if type(raw["tier"]) is not str or raw["tier"] not in _TIERS:
            raise ValueError("unknown memory tier")
        _identifier(raw["label"])
        tags = raw["tags"]
        if (type(tags) is not list or len(tags) > 12 or
                any(type(t) is not str or not _ID.fullmatch(t) for t in tags) or
                tags != sorted(set(tags))):
            raise ValueError("memory tags must be sorted identifiers")
        if (type(raw["anchor_sha"]) is not str or len(raw["anchor_sha"]) != 64 or
                any(ch not in "0123456789abcdef" for ch in raw["anchor_sha"])):
            raise ValueError("invalid anchor hash")
        if (type(raw["outcome"]) is not str or raw["outcome"] not in _OUTCOMES or
                raw["provenance"] != "LOCAL_OBSERVATION_UNVERIFIED"):
            raise ValueError("memory cannot self-certify an outcome")
        if (raw["tier"] == "NEGATIVE" and raw["outcome"] != "FAILURE_OBSERVED"):
            raise ValueError("negative memory needs observed failure")
        stamp, ttl = raw["captured_at"], raw["ttl_seconds"]
        if type(stamp) is not int or not 0 <= stamp <= 9999999999:
            raise ValueError("invalid memory timestamp")
        if raw["tier"] == "WORKING":
            if type(ttl) is not int or not 1 <= ttl <= 86400:
                raise ValueError("working memory requires bounded TTL")
        elif ttl is not None:
            raise ValueError("persistent tier must not imply automatic TTL deletion")
        encoded = canonical_bytes(raw)
        if len(encoded) > 2048:
            raise ValueError("memory record exceeded byte bound")
        return encoded

    def remember(self, *, tier: str, anchor_sha: str, label: str,
                 tags: tuple[str, ...] = (), outcome: str = "UNKNOWN",
                 captured_at: int | None = None, ttl_seconds: int | None = None) -> str:
        stamp = int(time.time()) if captured_at is None else captured_at
        raw = {"version": 1, "tier": tier, "anchor_sha": anchor_sha,
               "label": label, "tags": list(tags), "outcome": outcome,
               "captured_at": stamp, "ttl_seconds": ttl_seconds,
               "provenance": "LOCAL_OBSERVATION_UNVERIFIED"}
        payload = self._validate(raw)
        self.store.get(anchor_sha)  # verified immutable node, not trusted outcome
        digest = hashlib.sha256(payload).hexdigest()
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO entries VALUES(?,?,?,?,?,?)",
                            (digest, anchor_sha, tier, label, stamp, payload))
        return digest

    def get(self, digest: str) -> dict:
        if type(digest) is not str or len(digest) != 64 or any(
                x not in "0123456789abcdef" for x in digest):
            raise ValueError("invalid memory record hash")
        row = self.db.execute("SELECT payload,anchor_sha,tier,label,captured_at "
                              "FROM entries WHERE sha256=?", (digest,)).fetchone()
        if row is None:
            raise KeyError("memory hash not found")
        payload, anchor, tier, label, stamp = row
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("memory payload modified")
        raw = strict_json(payload, max_bytes=2048)
        if (self._validate(raw) != payload or
                (raw["anchor_sha"], raw["tier"], raw["label"], raw["captured_at"]) !=
                (anchor, tier, label, stamp)):
            raise ValueError("memory index differs from original content")
        self.store.get(anchor)  # refuse reuse when AXNODE content is corrupted
        return raw

    def find(self, query: str, *, tier: str | None = None,
             now: int | None = None, limit: int = 12) -> tuple[dict, ...]:
        if type(query) is not str or len(query) > 64 or (
                query and not _ID.fullmatch(query)):
            raise ValueError("memory query must be a bounded identifier")
        if tier is not None and tier not in _TIERS:
            raise ValueError("unknown memory tier")
        if type(limit) is not int or not 1 <= limit <= 25:
            raise ValueError("invalid memory result bound")
        stamp = int(time.time()) if now is None else now
        if type(stamp) is not int or stamp < 0:
            raise ValueError("invalid observation clock")
        rows = self.db.execute("SELECT sha256 FROM entries ORDER BY sha256 "
                               "LIMIT ?", (_LIMIT + 1,)).fetchall()
        if len(rows) > _LIMIT:
            raise ValueError("memory scan budget exhausted")
        found = []
        for (digest,) in rows:
            raw = self.get(digest)
            if tier is not None and tier != raw["tier"]:
                continue
            if (raw["tier"] == "WORKING" and
                    stamp >= raw["captured_at"] + raw["ttl_seconds"]):
                continue  # retained for owner-directed deletion, not reusable
            if query and query not in raw["label"] and not any(
                    query in tag for tag in raw["tags"]):
                continue
            found.append((raw["tier"], raw["captured_at"], digest, raw))
        found.sort(key=lambda item: (item[0], -item[1], item[2]))
        return tuple(item[3] for item in found[:limit])
