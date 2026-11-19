"""Immutable local AXNODE graph store. Independent of EAI legacy Store.

Only user-selected root, new files and draft/candidate nodes are handled.
No executable node, network access, promotion or writes to original EAI DB.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from .axnode_schema import MAX_NODE_BYTES, AXNode, parse_axnode
from .local_files import local_path, read_bytes, sqlite_snapshot

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SCHEMA_VERSION = 1


def _hash(value: str) -> str:
    if type(value) is not str or not _DIGEST.fullmatch(value):
        raise ValueError("invalid AXNODE SHA256")
    return value


class AXNodeStore:
    """Immutable, additive SQLite WAL index + content-addressed AXNODE files."""

    def __init__(self, root: str | Path, *, read_only: bool = False):
        self.read_only = read_only
        if read_only:
            self.root = local_path(root)
            self.nodes_dir = local_path(self.root / "nodes")
            self.db_path = local_path(self.root / "axnodes.sqlite")
            if not self.nodes_dir.is_dir():
                raise ValueError("existing AXNODE library required")
            self._snapshot = sqlite_snapshot(self.db_path)
            self.db = self._snapshot.__enter__()
            try:
                if self.db.execute("PRAGMA user_version").fetchone() != (1,):
                    raise ValueError("unknown AXNODE schema")
                expected = {"nodes": {"sha256", "node_id", "version", "status", "kind",
                                      "output_type", "search_text"},
                            "parents": {"child_sha", "parent_sha"}}
                tables = {r[1]: r[2] for r in self.db.execute("PRAGMA main.table_list")}
                for table, columns in expected.items():
                    if (tables.get(table) != "table" or
                            {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")} != columns):
                        raise ValueError("unexpected AXNODE catalog layout")
                self.db.execute("PRAGMA query_only=ON")
            except BaseException:
                self.close()
                raise
            return
        root = Path(root).expanduser()
        if root.is_symlink():
            raise ValueError("AXNODE store root cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.nodes_dir = self.root / "nodes"
        if self.nodes_dir.is_symlink():
            raise ValueError("AXNODE nodes directory cannot be a symlink")
        self.nodes_dir.mkdir(exist_ok=True)
        self.db_path = self.root / "axnodes.sqlite"
        if self.db_path.is_symlink():
            raise ValueError("AXNODE database cannot be a symlink")
        existing = self.db_path.exists() and self.db_path.stat().st_size > 0
        self.db = sqlite3.connect(self.db_path, timeout=3)
        try:
            self.db.execute("PRAGMA busy_timeout = 3000")
            self.db.execute("PRAGMA foreign_keys = ON")
            version = int(self.db.execute("PRAGMA user_version").fetchone()[0])
            if existing and version != _SCHEMA_VERSION:
                raise ValueError("unknown AXNODE DB version; do not migrate without backup")
            self.db.execute("PRAGMA journal_mode = WAL")
            if version == 0:
                self.db.executescript("""
                    CREATE TABLE nodes (
                      sha256 TEXT PRIMARY KEY, node_id TEXT NOT NULL,
                      version INTEGER NOT NULL, status TEXT NOT NULL,
                      kind TEXT NOT NULL, output_type TEXT NOT NULL,
                      search_text TEXT NOT NULL,
                      UNIQUE(node_id, version)
                    );
                    CREATE TABLE parents (
                      child_sha TEXT NOT NULL REFERENCES nodes(sha256),
                      parent_sha TEXT NOT NULL REFERENCES nodes(sha256),
                      PRIMARY KEY(child_sha, parent_sha)
                    );
                    CREATE INDEX parent_lookup ON parents(parent_sha);
                    PRAGMA user_version = 1;
                """)
                self.db.commit()
            else:
                cols = {row[1] for row in self.db.execute("PRAGMA table_info(nodes)")}
                if cols != {"sha256","node_id","version","status","kind","output_type","search_text"}:
                    raise ValueError("unexpected AXNODE DB layout")
        except Exception:
            self.db.close()
            raise

    def close(self) -> None:
        if self.read_only:
            self._snapshot.__exit__(None, None, None)
        else:
            self.db.close()

    def __enter__(self) -> "AXNodeStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _path(self, digest: str) -> Path:
        return self.nodes_dir / (_hash(digest) + ".axnode")

    @staticmethod
    def _keywords(raw: dict) -> str:
        sig = raw["signature"]
        return " ".join(
            [raw["id"], raw["kind"], sig["output"]]
            + list(sig["inputs"].keys()) + list(sig["inputs"].values())
            + raw["pre"] + raw["post"]
            + [step["skill"] for step in raw["steps"]]
        ).lower()[:4096]

    def import_node(self, source: str | bytes) -> str:
        """Validate before touching disk; never replace a node or overwrite a version."""
        if self.read_only:
            raise PermissionError("read-only AXNODE library")
        node = parse_axnode(source)
        raw = node.as_dict()
        digest = node.sha256
        output = raw["signature"]["output"]
        path = self._path(digest)
        # Only committed parents are allowed: this makes the graph acyclic by construction.
        parents = raw["parent_hashes"]
        for parent in parents:
            if self.db.execute("SELECT 1 FROM nodes WHERE sha256=?", (parent,)).fetchone() is None:
                raise ValueError("AXNODE parent not imported")
        row = self.db.execute(
            "SELECT sha256 FROM nodes WHERE node_id=? AND version=?",
            (raw["id"], raw["version"])
        ).fetchone()
        if row is not None and row[0] != digest:
            raise ValueError("immutable AXNODE version conflict")
        if path.is_symlink():
            raise ValueError("AXNODE content path is a symlink")
        if path.exists():
            if not path.is_file() or path.stat().st_size > MAX_NODE_BYTES or path.read_bytes() != node.canonical:
                raise ValueError("AXNODE on-disk content changed")
        else:
            fd, tmp = tempfile.mkstemp(prefix=".axnode-staging-", suffix=".tmp",
                                       dir=self.nodes_dir)
            try:
                with os.fdopen(fd, "wb") as file:
                    file.write(node.canonical)
                    file.flush()
                    os.fsync(file.fileno())
                # O_EXCL-like hard link avoids clobbering a concurrent node.
                try:
                    os.link(tmp, path)
                except FileExistsError:
                    if path.is_symlink() or path.read_bytes() != node.canonical:
                        raise ValueError("AXNODE concurrent content conflict")
            finally:
                Path(tmp).unlink(missing_ok=True)
        # A crash between file publication and the DB commit leaves an *orphan*,
        # never overwrites an existing version. audit() reports it for review.
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO nodes "
                "(sha256,node_id,version,status,kind,output_type,search_text) "
                "VALUES(?,?,?,?,?,?,?)",
                (digest,raw["id"],raw["version"],raw["status"],
                 raw["kind"],output,self._keywords(raw))
            )
            if self.db.execute("SELECT sha256 FROM nodes WHERE node_id=? AND version=?",
                               (raw["id"], raw["version"])).fetchone() != (digest,):
                raise ValueError("immutable AXNODE version conflict")
            for parent in parents:
                self.db.execute(
                    "INSERT OR IGNORE INTO parents(child_sha,parent_sha) VALUES(?,?)",
                    (digest,parent)
                )
        return digest

    def get(self, digest: str) -> AXNode:
        digest = _hash(digest)
        if self.db.execute("SELECT 1 FROM nodes WHERE sha256=?", (digest,)).fetchone() is None:
            raise KeyError("unindexed AXNODE hash")
        path = self._path(digest)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_NODE_BYTES:
            raise ValueError("AXNODE content missing or unsafe")
        node = parse_axnode(read_bytes(path, MAX_NODE_BYTES) if self.read_only else path.read_bytes())
        if node.sha256 != digest:
            raise ValueError("AXNODE content hash mismatch")
        if self.read_only:
            raw = node.as_dict()
            row = self.db.execute("SELECT node_id,version,status,kind,output_type FROM nodes "
                                  "WHERE sha256=?", (digest,)).fetchone()
            parents = tuple(p for p, in self.db.execute("SELECT parent_sha FROM parents "
                "WHERE child_sha=? ORDER BY parent_sha LIMIT 13", (digest,)))
            if (row != (raw["id"], raw["version"], raw["status"], raw["kind"], raw["signature"]["output"])
                    or parents != tuple(sorted(raw["parent_hashes"]))):
                raise ValueError("AXNODE metadata or lineage differs from its source")
        return node

    def hashes(self) -> list[str]:
        return [row[0] for row in self.db.execute(
            "SELECT sha256 FROM nodes ORDER BY node_id,version,sha256")]

    def parents_of(self, digest: str) -> tuple[str, ...]:
        self.get(digest)
        return tuple(row[0] for row in self.db.execute(
            "SELECT parent_sha FROM parents WHERE child_sha=? ORDER BY parent_sha",
            (digest,)))

    def children_of(self, digest: str) -> tuple[str, ...]:
        self.get(digest)
        return tuple(row[0] for row in self.db.execute(
            "SELECT child_sha FROM parents WHERE parent_sha=? ORDER BY child_sha",
            (digest,)))

    def audit(self) -> dict:
        """Read-only integrity report, never deletes orphan/suspect user data."""
        known = set(self.hashes())
        bad = []
        for digest in sorted(known):
            try:
                self.get(digest)
            except (ValueError, OSError):
                bad.append(digest)
        orphans = sorted(
            p.name for p in self.nodes_dir.iterdir()
            if (p.suffix == ".axnode" and p.stem not in known) or
               p.name.startswith(".axnode-staging-")
        )
        integrity = self.db.execute("PRAGMA integrity_check").fetchone()[0]
        fk = self.db.execute("PRAGMA foreign_key_check").fetchall()
        return {"indexed": len(known), "invalid_hashes": bad,
                "orphan_files": orphans,
                "sqlite_integrity": integrity,
                "foreign_key_violations": len(fk)}


# EAI-SWU-005: explicit additive import -> committed catalog -> fresh reload.
@dataclass(frozen=True)
class AXNodeReopenReceipt:
    node_sha256: str
    node_id: str
    version: int
    catalog_count: int
    parent_hashes: tuple[str, ...]
    status: str = "REOPENED_LOCAL_CONTENT_CONSISTENT_UNVERIFIED"
    real_execution_allowed: bool = False
    active_promotion_allowed: bool = False


def import_and_reopen_node(
    root: str | Path, source: str | bytes, *,
    allow_additive_import: bool = False,
) -> AXNodeReopenReceipt:
    """Opt-in existing isolated store only; no repair, overwrite or migration.

    A fresh connection must observe the exact immutable bytes, version row and
    graph edges after SQLite commit. Any incomplete/orphan store is held.
    """
    if type(allow_additive_import) is not bool or not allow_additive_import:
        raise PermissionError("explicit additive AXNODE import switch required")
    node = parse_axnode(source)  # reject hostile syntax before even opening disk
    canonical = node.canonical
    raw = node.as_dict()
    path = Path(root).expanduser()
    if (path.is_symlink() or not path.is_dir() or
            (path / "axnodes.sqlite").is_symlink() or
            not (path / "axnodes.sqlite").is_file() or
            (path / "nodes").is_symlink() or
            not (path / "nodes").is_dir()):
        raise ValueError("explicit pre-existing isolated AXNODE store required")
    with AXNodeStore(path) as writer:
        before = writer.audit()
        if (before["sqlite_integrity"] != "ok" or
                before["foreign_key_violations"] or before["invalid_hashes"] or
                before["orphan_files"]):
            raise ValueError("AXNODE pre-import integrity review required")
        previous_hashes = set(writer.hashes())
        digest = writer.import_node(source)
        if digest != node.sha256 or writer.get(digest).canonical != canonical:
            raise ValueError("AXNODE immediate import round-trip mismatch")
    # Reopen from disk rather than reuse a live in-memory SQLite connection.
    with AXNodeStore(path) as reader:
        loaded = reader.get(digest)
        if loaded.canonical != canonical or loaded.as_dict() != raw:
            raise ValueError("AXNODE fresh reload differs from imported source")
        row = reader.db.execute(
            "SELECT node_id,version,status,kind,output_type FROM nodes "
            "WHERE sha256=?", (digest,)).fetchone()
        expected = (raw["id"], raw["version"], raw["status"],
                    raw["kind"], raw["signature"]["output"])
        if row != expected:
            raise ValueError("AXNODE reopened catalog row mismatch")
        parents = reader.parents_of(digest)
        if parents != tuple(sorted(raw["parent_hashes"])):
            raise ValueError("AXNODE reopened graph edges differ")
        after = reader.audit()
        hashes_after = set(reader.hashes())
        if (after["sqlite_integrity"] != "ok" or
                after["foreign_key_violations"] or after["invalid_hashes"] or
                after["orphan_files"] or
                hashes_after - previous_hashes != (
                    set() if digest in previous_hashes else {digest}) or
                not previous_hashes.issubset(hashes_after)):
            raise ValueError("AXNODE import/reopen safety reconciliation failed")
        return AXNodeReopenReceipt(
            digest, raw["id"], raw["version"], len(hashes_after), parents)
