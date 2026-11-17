"""Explicit offline snapshot of private AXNODE sidecars, never original restore.

The existing v1 AXNODE archive omits memory/evidence. This complementary v1
bundle captures WAL-consistent SQLite snapshots into a NEW exclusive ZIP and
restores only to a NEW ISOLATED directory. It does not graft DBs into any live
store, delete originals, change account permissions, or prove provenance.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile

from .axnode_store import AXNodeStore
from .contracts import strict_json, canonical_bytes

_FILES = {
    "memory.sqlite": ("axnode_memory.sqlite", "entries",
                      {"sha256","anchor_sha","tier","label","captured_at","payload"}),
    "evidence.sqlite": ("evidence_ledger.sqlite", "observations",
                        {"sha256","claim_id","source_sha256","polarity",
                         "observed_at","expires_at","payload"}),
}
_MAX_DB = 16 * 1024 * 1024
_MAX_ZIP = 35 * 1024 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_sqlite(path: Path, kind: str) -> None:
    """Immutable offline snapshot validation; never auto-migrate."""
    _src, table, required = _FILES[kind]
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_DB:
        raise ValueError("unsafe or oversized sidecar")
    with closing(sqlite3.connect(
            path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=2)) as db:
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("unknown sidecar schema version")
        cols = {row[1] for row in db.execute('PRAGMA table_info("' + table + '")')}
        if cols != required:
            raise ValueError("unexpected sidecar table layout")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("sidecar integrity failure")
        count = db.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]
        if count > 3000:
            raise ValueError("sidecar row budget exceeded")
        if kind == "memory.sqlite":
            rows = db.execute(
                "SELECT sha256,anchor_sha,tier,label,captured_at,payload FROM entries"
            )
        else:
            rows = db.execute(
                "SELECT sha256,source_sha256,polarity,observed_at,expires_at,payload "
                "FROM observations"
            )
        for row in rows:
            digest, *metadata, payload = row
            if (type(digest) is not str or len(digest) != 64 or
                    type(payload) is not bytes or _sha(payload) != digest):
                raise ValueError("sidecar row content hash mismatch")
            parsed = strict_json(payload, max_bytes=2048)
            if canonical_bytes(parsed) != payload:
                raise ValueError("sidecar payload is not canonical")
            if kind == "memory.sqlite":
                expected = (parsed.get("anchor_sha"), parsed.get("tier"),
                            parsed.get("label"), parsed.get("captured_at"))
                if parsed.get("provenance") != "LOCAL_OBSERVATION_UNVERIFIED":
                    raise ValueError("forged memory provenance")
            else:
                expected = (parsed.get("source_sha256"), parsed.get("polarity"),
                            parsed.get("observed_at"), parsed.get("expires_at"))
                if parsed.get("origin") != "LOCAL_UNTRUSTED_OBSERVATION":
                    raise ValueError("forged evidence provenance")
            if tuple(metadata) != expected:
                raise ValueError("sidecar index/record metadata mismatch")


def create_sidecar_bundle(store: AXNodeStore, destination: str | Path) -> Path:
    """Non-destructive SQLite online backup of explicitly supplied local store."""
    if type(store) is not AXNodeStore:
        raise ValueError("explicit AXNODE store required")
    dest = Path(destination).expanduser()
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("backup destination exists")
    if not dest.parent.is_dir() or dest.parent.is_symlink():
        raise ValueError("backup parent must exist without symlink")
    if dest.resolve(strict=False).is_relative_to(store.root):
        raise ValueError("backup inside active AXNODE store forbidden")
    stage = Path(tempfile.mkdtemp(prefix=".eai-sidecar-", dir=dest.parent))
    try:
        present = {}
        for archive_name, (original, _table, _columns) in _FILES.items():
            path = store.root / original
            if path.is_symlink():
                raise ValueError("sidecar symlink rejected")
            if not path.exists():
                continue
            if not path.is_file() or path.stat().st_size > _MAX_DB:
                raise ValueError("oversized or nonregular sidecar")
            snapshot = stage / archive_name
            # SQLite online backup captures committed WAL transactions without
            # copying potentially stale db and separate WAL bytes.
            with closing(sqlite3.connect(
                    path.resolve(strict=True).as_uri() + "?mode=ro",
                    uri=True, timeout=3)) as source:
                with closing(sqlite3.connect(snapshot, timeout=3)) as target:
                    source.backup(target, pages=32, sleep=0.05)
                    target.commit()
            _check_sqlite(snapshot, archive_name)
            present[archive_name] = _sha(snapshot.read_bytes())
        if not present:
            raise ValueError("no optional sidecars to snapshot")
        manifest = {
            "format": "eai.axnode.sidecars.v1",
            "files": present,
            "disposition": "ISOLATED_PRIVATE_UNBOUND",
        }
        package = stage / "sidecars.zip"
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_STORED) as z:
            z.writestr("manifest.json", json.dumps(
                manifest, sort_keys=True, separators=(",", ":")))
            for name in sorted(present):
                z.write(stage / name, name)
        if package.stat().st_size > _MAX_ZIP:
            raise ValueError("sidecar bundle too large")
        # Private bundles can contain observed outcomes and references.
        os.chmod(package, 0o600)
        # Atomic no-overwrite publication; no original or existing backup touched.
        os.link(package, dest)
        return dest
    finally:
        shutil.rmtree(stage)


def restore_sidecar_bundle(archive: str | Path,
                           destination: str | Path) -> Path:
    """Restore to a NEW isolation folder only; never into running AXNODE root."""
    src = Path(archive).expanduser()
    dest = Path(destination).expanduser()
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("isolated sidecar restore destination exists")
    if not dest.parent.is_dir() or dest.parent.is_symlink():
        raise ValueError("restore parent must exist and not be a symlink")
    if src.is_symlink() or not src.is_file() or src.stat().st_size > _MAX_ZIP:
        raise ValueError("invalid or oversized archive")
    stage = Path(tempfile.mkdtemp(prefix=".eai-sidecar-restore-", dir=dest.parent))
    try:
        with zipfile.ZipFile(src, "r") as z:
            infos = z.infolist()
            names = [entry.filename for entry in infos]
            if (len(set(names)) != len(names) or len(names) > 3 or
                    any(entry.is_dir() or entry.compress_type != zipfile.ZIP_STORED or
                        entry.file_size > _MAX_DB for entry in infos) or
                    sum(item.file_size for item in infos) > _MAX_ZIP):
                raise ValueError("unsafe sidecar archive inventory")
            if "manifest.json" not in names:
                raise ValueError("missing sidecar manifest")
            try:
                manifest = json.loads(z.read("manifest.json"))
            except (ValueError, UnicodeError) as exc:
                raise ValueError("invalid sidecar manifest JSON") from exc
            if (type(manifest) is not dict or
                    set(manifest) != {"format","files","disposition"} or
                    manifest["format"] != "eai.axnode.sidecars.v1" or
                    manifest["disposition"] != "ISOLATED_PRIVATE_UNBOUND" or
                    type(manifest["files"]) is not dict or
                    not manifest["files"] or
                    set(manifest["files"]) - set(_FILES) or
                    set(names) != {"manifest.json",*manifest["files"]}):
                raise ValueError("unexpected sidecar inventory")
            for name, digest in sorted(manifest["files"].items()):
                if (type(digest) is not str or len(digest) != 64 or
                        any(ch not in "0123456789abcdef" for ch in digest)):
                    raise ValueError("invalid sidecar digest")
                payload = z.read(name)
                if len(payload) > _MAX_DB or _sha(payload) != digest:
                    raise ValueError("sidecar archive modified")
                (stage / name).write_bytes(payload)
                _check_sqlite(stage / name, name)
        # mkdir is exclusive: rename could replace an empty directory that
        # appeared between the exists check and rename on POSIX.
        os.mkdir(dest, mode=0o700)
        for name in sorted(manifest["files"]):
            os.link(stage / name, dest / name)
        return dest
    finally:
        if stage.exists():
            shutil.rmtree(stage)
