"""Deterministic, separate EAI customer review ZIP candidate, no real data.

Builds the existing P27 Python zipapp from source, then copies only
approved code/launcher/README + synthetic fixtures. No network or installer.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import os
from pathlib import Path
import tempfile
import sys
from zipfile import ZipFile, ZipInfo, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
NAME = "EAI-Offline-Review-0.1.0-beta.zip"


def _load(path, alias):
    spec = spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ValueError("LOCAL_COMPONENT_MISSING")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load(ROOT / "scripts/verify_customer_candidate.py", "_eai_candidate_verifier")
portable = _load(ROOT / "scripts/build_portable.py", "_eai_candidate_zipapp_builder")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def package_bytes():
    with tempfile.TemporaryDirectory(prefix="eai_candidate_") as tmp:
        target = Path(tmp) / "eai.pyz"
        portable.build_portable(ROOT, target)
        members = {
            "eai.pyz": target.read_bytes(),
            "verify_candidate.py": (ROOT / "scripts/verify_customer_candidate.py").read_bytes(),
            "RUN_EAI_REVIEW.cmd": (ROOT / "RUN_EAI_REVIEW.cmd").read_bytes(),
            "CUSTOMER_REVIEW_README.md": (ROOT / "CUSTOMER_REVIEW_README.md").read_bytes(),
            "samples/sample_key_coverage_goal.json": (ROOT / "examples/sample_key_coverage_goal.json").read_bytes(),
            "samples/sample_master_keys.csv": (ROOT / "examples/sample_master_keys.csv").read_bytes(),
            "samples/sample_detail_keys.csv": (ROOT / "examples/sample_detail_keys.csv").read_bytes(),
        }
    if set(members) != set(verifier.FILES):
        raise ValueError("unexpected candidate payload allowlist")
    for name, data in members.items():
        if len(data) > verifier.MAX_MEMBER:
            raise ValueError("source exceeded candidate member limit")
        if name.endswith(".cmd"):
            members[name] = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if name.endswith((".md", ".json", ".csv", ".py")):
            members[name] = data.replace(b"\r\n", b"\n")
            members[name].decode("utf-8")
    manifest = {
        "format": verifier.FORMAT, "version": verifier.VERSION,
        "release_approved": False,
        "files": {name: {"bytes": len(raw), "sha256": _sha(raw)}
                  for name, raw in sorted(members.items())},
    }
    members[verifier.MANIFEST] = (json.dumps(
        manifest, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")) + "\n").encode("utf-8")
    out = io.BytesIO()
    with ZipFile(out, "w", compression=ZIP_STORED, allowZip64=False) as z:
        for name in sorted(members):
            info = ZipInfo(verifier.PREFIX + name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, members[name])
    data = out.getvalue()
    if len(data) > verifier.MAX_ARCHIVE:
        raise ValueError("candidate ZIP exceeds bounded size")
    return data


def _publish_new(paths):
    stages, published = [], []
    try:
        for path, raw in paths:
            if path.exists() or path.is_symlink() or not path.parent.is_dir():
                raise ValueError("candidate output must be a NEW file in an existing folder")
            fd, name = tempfile.mkstemp(prefix=".eai-candidate-", suffix=".tmp",
                                        dir=path.parent)
            stage = Path(name)
            stages.append(stage)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        for (path, _), stage in zip(paths, stages):
            record = stage.stat()
            os.link(stage, path)
            published.append((path, record.st_dev, record.st_ino))
    except Exception:
        for path, device, inode in published:
            try:
                record = path.stat()
                if (record.st_dev, record.st_ino) == (device, inode):
                    path.unlink()
            except OSError:
                pass
        raise
    finally:
        for path in stages:
            path.unlink(missing_ok=True)


def build(output):
    dest = Path(output).absolute()
    if dest.name != NAME:
        raise ValueError("use fixed synthetic customer candidate ZIP filename")
    raw = package_bytes()
    digest = _sha(raw)
    detached = dest.with_name(dest.name + ".sha256")
    _publish_new([(dest, raw),
                  (detached, (digest + "  " + dest.name + "\n").encode("ascii"))])
    verified = verifier.verify_archive(dest, detached)
    return {"status": "EAI_REVIEW_CANDIDATE_BUILT_VERIFIED_UNSIGNED",
            "files": verified["files"], "bytes": len(raw),
            "sha256": digest, "release_approved": False}


def main(argv=None):
    p = argparse.ArgumentParser(description="Build unsigned EAI review beta ZIP")
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    try:
        print(json.dumps(build(args.output), sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "REJECTED", "error_code": "EAI_CANDIDATE_BUILD_FAILED"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
