"""Read-only post-restore audit of *isolated* AXNODE memory/evidence bundles.

Checks offline archive-to-extracted bytes, SQLite schema/row hash and that
every metadata anchor still maps to an existing immutable source AXNODE.
Does not import into a live store, repair a DB, rewrite originals or prove
semantic trust/independent evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

from .axnode_store import AXNodeStore
from .axnode_sidecar_backup import _FILES, _MAX_DB, _MAX_ZIP, _check_sqlite


@dataclass(frozen=True)
class SidecarRecoveryAudit:
    status: str
    archived_file_count: int
    validated_row_count: int
    matched_anchor_count: int
    paths: tuple[str, ...]
    bound_into_live_store: bool = False
    original_data_modified: bool = False


def audit_isolated_sidecar_restore(
        store: AXNodeStore, archive: str | Path, isolated_root: str | Path
        ) -> SidecarRecoveryAudit:
    if type(store) is not AXNodeStore:
        raise ValueError("explicit original AXNODE store required")
    bundle, root = Path(archive).expanduser(), Path(isolated_root).expanduser()
    if (bundle.is_symlink() or not bundle.is_file() or
            bundle.stat().st_size > _MAX_ZIP or root.is_symlink() or
            not root.is_dir() or root.resolve(strict=True) == store.root or
            root.resolve(strict=True).is_relative_to(store.root)):
        raise ValueError("only separate regular archive and isolated restore allowed")
    if bundle.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise ValueError("archive inside restore is unsupported")
    if any(entry.is_symlink() or not entry.is_file() for entry in root.iterdir()):
        raise ValueError("untrusted restore entry")
    names = {entry.name for entry in root.iterdir()}
    with zipfile.ZipFile(bundle, "r") as z:
        infos = z.infolist()
        archive_names = [info.filename for info in infos]
        if (len(archive_names) != len(set(archive_names)) or
                len(archive_names) > 3 or "manifest.json" not in archive_names or
                any(info.is_dir() or info.compress_type != zipfile.ZIP_STORED or
                    info.file_size > _MAX_DB for info in infos)):
            raise ValueError("untrusted archive entries")
        if z.getinfo("manifest.json").file_size > 2048:
            raise ValueError("oversized manifest")
        try:
            manifest = json.loads(z.read("manifest.json"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("invalid manifest") from exc
        if (type(manifest) is not dict or
                set(manifest) != {"format", "files", "disposition"} or
                manifest["format"] != "eai.axnode.sidecars.v1" or
                manifest["disposition"] != "ISOLATED_PRIVATE_UNBOUND" or
                type(manifest["files"]) is not dict or not manifest["files"] or
                set(manifest["files"]) - set(_FILES) or
                set(archive_names) != {"manifest.json", *manifest["files"]} or
                names != set(manifest["files"])):
            raise ValueError("incomplete or unexpected restored sidecars")
        archive_digests = manifest["files"]
        count, anchors = 0, set()
        for name, digest in sorted(archive_digests.items()):
            if (type(digest) is not str or len(digest) != 64 or
                    any(ch not in "0123456789abcdef" for ch in digest)):
                raise ValueError("invalid source digest")
            file = root / name
            if file.is_symlink() or not file.is_file() or file.stat().st_size > _MAX_DB:
                raise ValueError("unsafe restored file")
            restored_bytes = file.read_bytes()
            if (hashlib.sha256(restored_bytes).hexdigest() != digest or
                    hashlib.sha256(z.read(name)).hexdigest() != digest):
                raise ValueError("restore does not match archived content")
            _check_sqlite(file, name)
            # Opening this *offline* DB read-only cannot attach it to the live
            # original. Every anchor must exist, but that is not outcome truth.
            with closing(sqlite3.connect(file.resolve(strict=True).as_uri() +
                                 "?mode=ro&immutable=1", uri=True)) as db:
                field, table = (("anchor_sha", "entries") if name == "memory.sqlite"
                                else ("source_sha256", "observations"))
                rows = db.execute("SELECT " + field + " FROM " + table).fetchall()
            if len(rows) > 3000:
                raise ValueError("restored row count budget exceeded")
            for (anchor,) in rows:
                store.get(anchor)
                anchors.add(anchor)
            count += len(rows)
    return SidecarRecoveryAudit("ISOLATED_RESTORE_INTEGRITY_ONLY_UNVERIFIED",
                                len(archive_digests), count, len(anchors),
                                tuple(sorted(archive_digests)))
