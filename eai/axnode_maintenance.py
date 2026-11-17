"""Fail-closed synthetic AXNODE lineage and offline backup/restore.

Never mutates an existing store, changes node status, or overwrites a backup.
A descendant impact is only a review plan, not automatic quarantine/promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile

from .axnode_schema import MAX_NODE_BYTES, parse_axnode
from .axnode_store import AXNodeStore

_MAX_NODES = 3000
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class LineageImpact:
    source_sha256: str
    affected_sha256: tuple[str, ...]
    disposition: str = "REVIEW_REQUIRED_NOT_EXECUTED"


def plan_parent_invalidation(store: AXNodeStore, source_sha256: str) -> LineageImpact:
    """Return complete descendants; do not silently alter immutable evidence."""
    if type(store) is not AXNodeStore:
        raise ValueError("explicit local AXNODE store required")
    store.get(source_sha256)
    seen = {source_sha256}
    pending = [source_sha256]
    while pending:
        parent = pending.pop(0)
        for child in store.children_of(parent):
            node = store.get(child)
            if parent not in node.as_dict()["parent_hashes"]:
                raise ValueError("AXNODE lineage metadata mismatch")
            if child not in seen:
                seen.add(child)
                if len(seen) > _MAX_NODES:
                    raise ValueError("AXNODE lineage exceeds bounded review budget")
                pending.append(child)
    return LineageImpact(source_sha256, tuple(sorted(seen - {source_sha256})))


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _store_snapshot_ok(store: AXNodeStore, digests: list[str]) -> None:
    state = store.audit()
    if (state["sqlite_integrity"] != "ok" or state["invalid_hashes"] or
            state["foreign_key_violations"] or state["orphan_files"]):
        raise ValueError("AXNODE store has unreviewed integrity findings")
    if len(digests) > _MAX_NODES:
        raise ValueError("AXNODE store exceeds bounded backup budget")


def create_offline_backup(store: AXNodeStore, destination: str | Path) -> Path:
    """SQLite online snapshot + pinned node files; exclusive publication of ZIP."""
    if type(store) is not AXNodeStore:
        raise ValueError("explicit local AXNODE store required")
    destination = Path(destination).expanduser()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("AXNODE backup already exists")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("backup parent must be an existing real directory")
    if destination.resolve(strict=False).is_relative_to(store.root):
        raise ValueError("backup cannot be inside AXNODE source")
    stage = Path(tempfile.mkdtemp(prefix=".eai-backup-", dir=destination.parent))
    try:
        db_file = stage / "catalog.sqlite"
        with sqlite3.connect(db_file) as snapshot:
            store.db.backup(snapshot)
            snapshot.execute("PRAGMA foreign_keys = ON")
            if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("backup SQLite integrity failure")
            if snapshot.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("backup SQLite foreign-key failure")
            rows = snapshot.execute("SELECT sha256 FROM nodes ORDER BY sha256").fetchall()
            digests = [row[0] for row in rows]
        _store_snapshot_ok(store, digests)
        if set(digests) != set(store.hashes()):
            raise ValueError("AXNODE store changed during backup; retry from clean state")
        db_bytes = db_file.read_bytes()
        manifest = {"format": "eai.axnode.backup.v1", "db_sha256": _digest(db_bytes),
                    "node_sha256": digests}
        archive = stage / "backup.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as target:
            target.writestr("manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")))
            target.writestr("catalog.sqlite", db_bytes)
            for digest in digests:
                node = store.get(digest)
                if node.sha256 != digest:
                    raise ValueError("AXNODE content changed during backup")
                target.writestr("nodes/" + digest + ".axnode", node.canonical)
        if archive.stat().st_size > _MAX_ARCHIVE_BYTES:
            raise ValueError("backup exceeds safe offline size")
        # Atomic exclusive creation; no change to existing source or target.
        os.link(archive, destination)
        return destination
    finally:
        shutil.rmtree(stage)


def restore_offline_backup(archive: str | Path, destination: str | Path) -> Path:
    """Restore into a *new* root; reject untrusted zip paths and corruption."""
    archive = Path(archive).expanduser()
    destination = Path(destination).expanduser()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("refusing to replace an AXNODE store")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("restore parent must be an existing real directory")
    if not archive.is_file() or archive.is_symlink() or archive.stat().st_size > _MAX_ARCHIVE_BYTES:
        raise ValueError("invalid AXNODE archive")
    stage = Path(tempfile.mkdtemp(prefix=".eai-restore-", dir=destination.parent))
    try:
        with zipfile.ZipFile(archive, "r") as source:
            infos = source.infolist()
            names = [entry.filename for entry in infos]
            if (len(set(names)) != len(names) or len(infos) > _MAX_NODES + 2 or
                    any(entry.compress_type != zipfile.ZIP_STORED or entry.is_dir()
                        or entry.file_size > _MAX_ARCHIVE_BYTES for entry in infos) or
                    sum(entry.file_size for entry in infos) > _MAX_ARCHIVE_BYTES):
                raise ValueError("unsafe AXNODE backup inventory")
            if "manifest.json" not in names or "catalog.sqlite" not in names:
                raise ValueError("incomplete AXNODE archive")
            manifest = json.loads(source.read("manifest.json"))
            if (type(manifest) is not dict or set(manifest) !=
                    {"format", "db_sha256", "node_sha256"} or
                    manifest["format"] != "eai.axnode.backup.v1" or
                    type(manifest["node_sha256"]) is not list or
                    len(manifest["node_sha256"]) > _MAX_NODES):
                raise ValueError("invalid AXNODE manifest")
            digests = manifest["node_sha256"]
            if (any(type(h) is not str or len(h) != 64 or
                    any(c not in "0123456789abcdef" for c in h) for h in digests) or
                    digests != sorted(set(digests))):
                raise ValueError("invalid AXNODE digest inventory")
            expected = {"manifest.json", "catalog.sqlite"} | {
                "nodes/" + h + ".axnode" for h in digests}
            if set(names) != expected:
                raise ValueError("unexpected AXNODE archive entry")
            db_bytes = source.read("catalog.sqlite")
            if _digest(db_bytes) != manifest["db_sha256"]:
                raise ValueError("modified AXNODE SQLite backup")
            (stage / "nodes").mkdir()
            (stage / "axnodes.sqlite").write_bytes(db_bytes)
            for digest in digests:
                blob = source.read("nodes/" + digest + ".axnode")
                if len(blob) > MAX_NODE_BYTES or parse_axnode(blob).sha256 != digest:
                    raise ValueError("modified AXNODE content in backup")
                (stage / "nodes" / (digest + ".axnode")).write_bytes(blob)
        with AXNodeStore(stage) as restored:
            if set(restored.hashes()) != set(digests):
                raise ValueError("AXNODE backup index differs from manifest")
            for digest in digests:
                node = restored.get(digest).as_dict()
                row = restored.db.execute(
                    "SELECT node_id,version,status,kind,output_type FROM nodes WHERE sha256=?",
                    (digest,)).fetchone()
                if row != (node["id"],node["version"],node["status"],
                           node["kind"],node["signature"]["output"]):
                    raise ValueError("AXNODE backup metadata mismatch")
                if restored.parents_of(digest) != tuple(sorted(node["parent_hashes"])):
                    raise ValueError("AXNODE backup parent graph mismatch")
            _store_snapshot_ok(restored, digests)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("restore destination appeared during validation")
        os.rename(stage, destination)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)
