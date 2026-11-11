"""Verify separately-versioned EAI customer beta ZIP or pristine extraction.

Bounded, fixed synthetic-only member allowlist. Checks transport integrity,
not a digital signature, provenance, antivirus, license or customer approval.
This verifier is included in the same unsigned archive for startup preflight.
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

VERSION = "0.1.0-review-beta"
FORMAT = "EAI_CUSTOMER_REVIEW_V1"
PREFIX = "EAI-REVIEW-LOCAL/"
FILES = (
    "eai.pyz",
    "verify_candidate.py",
    "RUN_EAI_REVIEW.cmd",
    "CUSTOMER_REVIEW_README.md",
    "samples/sample_key_coverage_goal.json",
    "samples/sample_master_keys.csv",
    "samples/sample_detail_keys.csv",
)
MANIFEST = "MANIFEST.json"
MAX_MEMBER = 2_097_152
MAX_ARCHIVE = 6_291_456
HEX = re.compile(r"^[0-9a-f]{64}$")


class CandidateError(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_manifest(raw):
    if len(raw) > 16384:
        raise CandidateError("MANIFEST_TOO_LARGE")
    def unique(pairs):
        data = {}
        for key, val in pairs:
            if key in data:
                raise CandidateError("MANIFEST_DUPLICATE_KEY")
            data[key] = val
        return data
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateError("MANIFEST_INVALID") from exc
    if (type(obj) is not dict or set(obj) != {"format", "version", "files",
                                            "release_approved"} or
            obj["format"] != FORMAT or obj["version"] != VERSION or
            obj["release_approved"] is not False or
            type(obj["files"]) is not dict or set(obj["files"]) != set(FILES)):
        raise CandidateError("MANIFEST_SCHEMA")
    for item in obj["files"].values():
        if (type(item) is not dict or set(item) != {"sha256", "bytes"} or
                type(item["sha256"]) is not str or
                HEX.fullmatch(item["sha256"]) is None or
                type(item["bytes"]) is not int or
                not 0 <= item["bytes"] <= MAX_MEMBER):
            raise CandidateError("MANIFEST_ENTRY")
    return obj


def _linked(path):
    info = Path(path).lstat()
    return (stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) &
        getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)))


def verify_archive(path, checksum=None):
    archive = Path(path)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE:
        raise CandidateError("ARCHIVE_UNAVAILABLE")
    binary = archive.read_bytes()
    digest = _sha(binary)
    if checksum is not None:
        detached = Path(checksum)
        if (detached.is_symlink() or not detached.is_file() or
                detached.stat().st_size > 256):
            raise CandidateError("CHECKSUM_UNAVAILABLE")
        expected = digest + "  " + archive.name + "\n"
        if not hmac.compare_digest(detached.read_bytes(), expected.encode("ascii")):
            raise CandidateError("CHECKSUM_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(binary)) as z:
            names = [item.filename for item in z.infolist()]
            expected = {PREFIX + name for name in FILES + (MANIFEST,)}
            if len(names) != len(expected) or set(names) != expected:
                raise CandidateError("ARCHIVE_INVENTORY")
            for item in z.infolist():
                mode = (item.external_attr >> 16) & 0o170000
                if (item.is_dir() or item.flag_bits & 1 or
                        item.compress_type != zipfile.ZIP_STORED or
                        item.file_size > MAX_MEMBER or
                        mode not in (0, 0o100000)):
                    raise CandidateError("ARCHIVE_ENTRY_INVALID")
            manifest = _read_manifest(z.read(PREFIX + MANIFEST))
            for name in FILES:
                raw = z.read(PREFIX + name)
                entry = manifest["files"][name]
                if (len(raw) != entry["bytes"] or
                        not hmac.compare_digest(_sha(raw), entry["sha256"])):
                    raise CandidateError("ARCHIVE_PAYLOAD_MISMATCH")
    except (zipfile.BadZipFile, EOFError, RuntimeError) as exc:
        raise CandidateError("ARCHIVE_INVALID") from exc
    return {"status": "CANDIDATE_ZIP_CONSISTENT_UNSIGNED",
            "files": len(FILES), "sha256": digest, "release_approved": False}


def verify_directory(path):
    root = Path(path).absolute()
    if not root.is_dir() or _linked(root):
        raise CandidateError("DIRECTORY_UNAVAILABLE")
    expected = set(FILES + (MANIFEST,))
    dirs = {"/".join(name.split("/")[:depth])
            for name in expected
            for depth in range(1, len(name.split("/")))}
    actual = set()
    for item in root.rglob("*"):
        rel = item.relative_to(root).as_posix()
        if _linked(item):
            raise CandidateError("LINKED_FILE_REFUSED")
        if item.is_dir():
            if rel not in dirs:
                raise CandidateError("UNKNOWN_DIRECTORY")
        elif item.is_file():
            if rel not in expected or item.stat().st_size > MAX_MEMBER:
                raise CandidateError("UNKNOWN_OR_LARGE_FILE")
            actual.add(rel)
        else:
            raise CandidateError("UNSUPPORTED_ENTRY")
    if actual != expected:
        raise CandidateError("DIRECTORY_INCOMPLETE")
    manifest = _read_manifest((root / MANIFEST).read_bytes())
    for name in FILES:
        raw = (root / name).read_bytes()
        if (len(raw) != manifest["files"][name]["bytes"] or
                not hmac.compare_digest(_sha(raw),
                     manifest["files"][name]["sha256"])):
            raise CandidateError("DIRECTORY_TAMPERED")
    return {"status": "CANDIDATE_DIRECTORY_CONSISTENT_UNSIGNED",
            "files": len(FILES), "release_approved": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="EAI read-only unsigned candidate verifier")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--archive")
    group.add_argument("--directory")
    parser.add_argument("--checksum")
    args = parser.parse_args(argv)
    try:
        if args.directory:
            if args.checksum:
                raise CandidateError("INVALID_VERIFY_ARGUMENTS")
            result = verify_directory(args.directory)
        else:
            result = verify_archive(args.archive, args.checksum)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (CandidateError, OSError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, CandidateError) else "CANDIDATE_VERIFICATION_REJECTED"
        print(json.dumps({"status": "REJECTED", "error_code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
