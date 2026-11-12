"""P32 local-only customer review bundle from independently verified EAI goals.

Fresh destination only. Source files remain untouched; no source CSV rows,
raw values, Qwen requests, or credentials are copied to the report. This is
a digest/consistency verifier, not a signed provenance or privacy certificate.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import stat

from .goal_dispatch import _read_spec
from .report_export import build_report, render_report_html, VERSION

OUTPUTS = ("review.json", "review.html", "manifest.json")
FORMAT = "eai.local_owner_review.v1"
MAX_BYTES = 2_097_152


class CustomerReviewError(ValueError):
    """Opaque errors; no raw source data in failure messages."""


def _read_json(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise CustomerReviewError("FILE_TOO_LARGE")
    def no_dupes(pairs):
        result = {}
        for key, val in pairs:
            if key in result:
                raise CustomerReviewError("DUPLICATE_JSON_KEY")
            result[key] = val
        return result
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=no_dupes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CustomerReviewError("INVALID_JSON") from exc
    if type(parsed) is not dict:
        raise CustomerReviewError("INVALID_JSON")
    return parsed


def _bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_path(path):
    value = Path(os.path.abspath(path))
    for component in (value, *value.parents):
        try:
            state = component.lstat()
        except FileNotFoundError:
            if component != value:
                raise CustomerReviewError("PARENT_NOT_PRESENT")
            continue
        if (stat.S_ISLNK(state.st_mode) or
                bool(getattr(state, "st_file_attributes", 0) &
                     getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))):
            raise CustomerReviewError("LINKED_PATH_REFUSED")
    return value


def _summary_schema(summary):
    if (type(summary) is not dict or
            set(summary) != {"version", "status", "kind", "document",
                             "verification", "items", "disclaimer", "policy"} or
            summary["version"] != VERSION or
            summary["verification"] != "PASS" or
            summary["status"] not in ("AGREE", "CONFLICT", "UNAVAILABLE", "DECIDED",
                                      "TIE", "REVIEW", "COMPLETE", "PARTIAL", "FAILED") or
            type(summary["kind"]) is not str or
            not 1 <= len(summary["kind"]) <= 80 or
            type(summary["document"]) is not dict or
            set(summary["document"]) != {"filename", "sha256"} or
            type(summary["document"]["filename"]) is not str or
            not 1 <= len(summary["document"]["filename"]) <= 255 or
            type(summary["document"]["sha256"]) is not str or
            len(summary["document"]["sha256"]) != 64 or
            any(ch not in "0123456789abcdef" for ch in summary["document"]["sha256"]) or
            type(summary["items"]) is not list or
            not 1 <= len(summary["items"]) <= 6 or
            type(summary["disclaimer"]) is not str or
            type(summary["policy"]) is not str):
        raise CustomerReviewError("REVIEW_SCHEMA_REJECTED")
    for row in summary["items"]:
        if (type(row) is not dict or
                set(row) != {"id", "kind", "status", "verification", "sha256"} or
                any(type(row[key]) is not str or len(row[key]) > 120
                    for key in row) or
                row["verification"] not in ("PASS", "NOT_RUN", "BLOCKED") or
                (row["sha256"] and
                 (len(row["sha256"]) != 64 or
                  any(x not in "0123456789abcdef" for x in row["sha256"])))):
            raise CustomerReviewError("REVIEW_ROW_REJECTED")
    return summary


def _write_new(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def create_review(goal_path, output_dir, *, acknowledge=False):
    if acknowledge is not True:
        raise CustomerReviewError("LOCAL_SOURCE_ACK_REQUIRED")
    goal = _safe_path(goal_path)
    if not goal.is_file() or goal.suffix.lower() != ".json":
        raise CustomerReviewError("GOAL_FILE_INVALID")
    target = _safe_path(output_dir)
    if target.exists() or target.is_symlink():
        raise CustomerReviewError("OUTPUT_ALREADY_EXISTS")
    if not target.parent.is_dir():
        raise CustomerReviewError("OUTPUT_PARENT_MISSING")
    # A source changes during analysis? build_report has source SHA checks.
    # Keep the hash across report creation, but not raw source bytes.
    _, before = _read_spec(goal)
    try:
        summary = _summary_schema(build_report(goal))
    except (OSError, ValueError, UnicodeError, TypeError, KeyError) as exc:
        raise CustomerReviewError("SOURCE_REVIEW_REJECTED") from exc
    if before != summary["document"]["sha256"] or _read_spec(goal)[1] != before:
        raise CustomerReviewError("SOURCE_HASH_CHANGED")
    json_raw = _bytes(summary)
    page = render_report_html(summary).encode("utf-8")
    if max(len(json_raw), len(page)) > MAX_BYTES:
        raise CustomerReviewError("REVIEW_TOO_LARGE")
    manifest_raw = _bytes({
        "schema_version": FORMAT, "signature_verified": False,
        "source_included": False,
        "files_sha256": {"review.json": _sha(json_raw),
                         "review.html": _sha(page)},
    })
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise CustomerReviewError("OUTPUT_ALREADY_EXISTS") from exc
    # Keep interruption evidence. Never remove pre-existing user files.
    _write_new(target / ".EAI_INCOMPLETE", b"EAI_REVIEW_INCOMPLETE\n")
    for name, raw in (("review.json", json_raw), ("review.html", page),
                      ("manifest.json", manifest_raw)):
        _write_new(target / name, raw)
    (target / ".EAI_INCOMPLETE").unlink()
    # Re-verify after publish. Cannot certify concurrent filesystem mutation.
    verify_review(target)
    return {"status": "REVIEW_CREATED_UNSIGNED",
            "decision_status": summary["status"], "files": list(OUTPUTS),
            "original_sources_copied": False, "network_called": False}


def verify_review(output_dir):
    target = _safe_path(output_dir)
    if not target.is_dir() or {p.name for p in target.iterdir()} != set(OUTPUTS):
        raise CustomerReviewError("INCOMPLETE_OR_EXTRA_FILES")
    values = {}
    for name in OUTPUTS:
        file = _safe_path(target / name)
        if not file.is_file() or file.stat().st_size > MAX_BYTES:
            raise CustomerReviewError("OUTPUT_INVALID")
        with file.open("rb") as stream:
            values[name] = stream.read(MAX_BYTES + 1)
        if len(values[name]) > MAX_BYTES:
            raise CustomerReviewError("OUTPUT_TOO_LARGE")
    manifest = _read_json(values["manifest.json"])
    if (set(manifest) != {"schema_version", "signature_verified",
                          "source_included", "files_sha256"} or
            manifest["schema_version"] != FORMAT or
            manifest["signature_verified"] is not False or
            manifest["source_included"] is not False or
            type(manifest["files_sha256"]) is not dict or
            set(manifest["files_sha256"]) != {"review.json", "review.html"}):
        raise CustomerReviewError("MANIFEST_SCHEMA_REJECTED")
    for name in ("review.json", "review.html"):
        digest = manifest["files_sha256"][name]
        if (type(digest) is not str or not
                hmac.compare_digest(digest, _sha(values[name]))):
            raise CustomerReviewError("REVIEW_INTEGRITY_MISMATCH")
    summary = _summary_schema(_read_json(values["review.json"]))
    if values["review.html"] != render_report_html(summary).encode("utf-8"):
        raise CustomerReviewError("REVIEW_RENDER_MISMATCH")
    return {"status": "REVIEW_CONSISTENT_UNSIGNED",
            "decision_status": summary["status"], "files": list(OUTPUTS),
            "origin_authenticated": False, "source_reopened": False}
