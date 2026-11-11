"""P23 owner-directed CSV source advisor: offline, read-only, no auto execution.

This advisor produces editable typed-goal JSON drafts. Only the user can save
and explicitly run them with solve-goal. The advisor never claims statistical
significance, real-world validity, or permission to repair the data.
"""
import csv
from decimal import Decimal
import hashlib
import io
from pathlib import Path

from .analysis import _NUMBER
from .csv_analysis import (
    ALLOWED_ENCODINGS, MAX_COLUMNS, MAX_FILE_BYTES, MAX_FIELD_CHARS, MAX_ROWS
)
from .csv_quality import source_snapshot
from .csv_relationships import validate_relationship_goal
from .csv_robust_outliers import validate_outlier_goal

VERSION = "eai.csv.advisor.v1"
POLICY = "READ_ONLY;NO_REMOTE;NO_AUTO_EXECUTE;USER_MUST_REVIEW_DRAFT"


def _source(root: str | Path, supplied: str) -> tuple[Path, Path]:
    if type(supplied) is not str or not 1 <= len(supplied) <= 512 or any(
        c in "\\:" or ord(c) < 32 for c in supplied
    ):
        raise ValueError("source must be a short local relative CSV filename")
    relative = Path(supplied)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".csv":
        raise ValueError("CSV source must remain inside selected root")
    folder = Path(root).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("selected root must be a directory")
    selected = (folder / relative).resolve(strict=True)
    if not selected.is_relative_to(folder) or selected.suffix.lower() != ".csv":
        raise ValueError("CSV source symlink escapes selected root")
    if not selected.is_file():
        raise ValueError("CSV source is not a regular file")
    return folder, selected


def _is_number(value: str) -> bool:
    if not value.strip() or not _NUMBER.fullmatch(value.strip()):
        return False
    try:
        return Decimal(value.strip()).is_finite()
    except (ArithmeticError, ValueError):
        return False


def advise_csv(root: str | Path, source: str, *, encoding: str = "utf-8-sig") -> dict:
    """Inspect one explicitly selected file and return bounded, unexecuted drafts.

    Never prints rows, scans directories, modifies data, calls APIs, or executes
    a generated goal. Drafts must be inspected and saved by the owner.
    """
    if type(encoding) is not str or encoding not in ALLOWED_ENCODINGS:
        raise ValueError("invalid CSV encoding")
    folder, selected = _source(root, source)
    if selected.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("CSV source exceeds size bound")
    binary, original_sha = source_snapshot(selected)
    previous_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader = csv.reader(io.StringIO(binary.decode(encoding), newline=""), strict=True)
        headers = next(reader, None)
        if headers is None or not 1 <= len(headers) <= MAX_COLUMNS:
            raise ValueError("CSV must have 1-32 headers")
        if any(
            not 1 <= len(name) <= 60 or name != name.strip() or
            any(ord(ch) < 32 for ch in name) for name in headers
        ) or len({name.casefold() for name in headers}) != len(headers):
            raise ValueError("CSV contains invalid or duplicate headers")
        total = 0
        available = [0] * len(headers)
        missing = [0] * len(headers)
        for cells in reader:
            total += 1
            if total > MAX_ROWS or len(cells) != len(headers):
                raise ValueError("CSV row/count bound or column mismatch")
            if any(len(cell) > MAX_FIELD_CHARS for cell in cells):
                raise ValueError("CSV cell exceeds length bound")
            for index, cell in enumerate(cells):
                if not cell.strip():
                    missing[index] += 1
                elif _is_number(cell):
                    available[index] += 1
    finally:
        csv.field_size_limit(previous_limit)
    # No captured row data is emitted. Re-read and hash before releasing advice.
    if source_snapshot(selected)[1] != original_sha:
        raise ValueError("CSV source changed during inspection")
    if len(binary) > MAX_FILE_BYTES:
        raise ValueError("CSV source exceeds size bound")
    cols = [
        {"header": name, "numeric_rows": available[i], "missing_rows": missing[i],
         "nonnumeric_rows": total - available[i] - missing[i]}
        for i, name in enumerate(headers)
    ]
    # Do not infer domain semantics. Only columns parseable as fixed-point
    # numbers in at least five records are potential candidates.
    candidates = [name for i, name in enumerate(headers) if available[i] >= 5]
    filename = selected.relative_to(folder).as_posix()
    drafts = []
    if len(candidates) >= 2:
        candidate = {
            "version": 1, "kind": "csv_relationships",
            "goal": "Review selected numeric relationships",
            "source": filename, "encoding": encoding,
            "columns": candidates[:6], "min_rows": 5,
        }
        validate_relationship_goal(candidate, folder / "_eai_unwritten_draft.json")
        drafts.append({"kind": "csv_relationships", "goal": candidate,
                       "review": "Correlation is not causality or predictive accuracy."})
    if candidates:
        candidate = {
            "version": 1, "kind": "csv_robust_outliers",
            "goal": "Review potential numeric outlier candidates",
            "source": filename, "encoding": encoding,
            "columns": candidates[:4], "min_rows": 5, "threshold": "3",
        }
        validate_outlier_goal(candidate, folder / "_eai_unwritten_draft.json")
        drafts.append({"kind": "csv_robust_outliers", "goal": candidate,
                       "review": "Review columns and threshold before explicit execution."})
    return {
        "version": VERSION, "status": "DRAFT_READY" if drafts else "REVIEW_REQUIRED",
        "source": {"filename": filename, "sha256": original_sha,
                   "bytes": len(binary), "rows": total},
        "columns": cols, "drafts": drafts, "policy": POLICY,
        "next_step": "Review a draft, save JSON beside the CSV, then explicitly call solve-goal."
    }


def render_csv_advice(report: dict) -> str:
    lines = [f"EAI CSV advisor: {report['status']}",
             f"Source: {report['source']['filename']} SHA256 {report['source']['sha256']}",
             f"Records: {report['source']['rows']}"]
    for item in report["columns"]:
        lines.append(f"{item['header']}: numeric={item['numeric_rows']}, "
                     f"missing={item['missing_rows']}, nonnumeric={item['nonnumeric_rows']}")
    lines.append("Editable draft kinds: " +
                 (", ".join(row["kind"] for row in report["drafts"]) or "none"))
    lines.append(report["next_step"])
    lines.append(report["policy"])
    return "\n".join(lines)
