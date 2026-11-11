"""P31 bounded read-only relational key coverage across two owner CSVs.

Checks parent/master unique keys and detail/child foreign-key coverage.
No joins are materialized, individual keys or row values are not returned.
This is a consistency check, not a claim that customer records are authentic.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
import csv
import io
from pathlib import Path
import stat

from .csv_analysis import ALLOWED_ENCODINGS, MAX_COLUMNS, MAX_ROWS, MAX_FIELD_CHARS
from .csv_quality import source_snapshot
from .decision_engine import _num

VERSION = "eai.goal.csv_key_coverage.v1"
SCOPE = (
    "두 로컬 CSV에서 마스터 고유키·상세 참조키의 누락, 중복, 참조 부재를 검사했습니다. "
    "개별 키·원본 행 값·레코드 본문은 보고하지 않습니다. 참조 일치가 실세계 진실성을 "
    "의미하지 않으며 파일 수정, 자동 복구, 외부 전송을 수행하지 않습니다."
)


@dataclass(frozen=True)
class KeyCoverageGoal:
    goal: str
    master: Path
    detail: Path
    master_key: str
    detail_key: str
    encoding: str
    min_coverage_percent: Decimal


def _safe_owner_csv(parent: Path, supplied: object) -> Path:
    if (type(supplied) is not str or not 1 <= len(supplied) <= 512 or
            any(x in supplied for x in ("\\", ":")) or
            any(ord(x) < 32 for x in supplied)):
        raise ValueError("invalid local CSV path")
    relative = Path(supplied)
    if (relative.is_absolute() or ".." in relative.parts or
            relative.suffix.lower() != ".csv"):
        raise ValueError("source must be a relative CSV inside owner folder")
    target = parent / relative
    # Prevent accidental symlink/junction traversal, not a TOCTOU guarantee.
    for component in (target, *[parent / Path(*relative.parts[:i])
                                  for i in range(1, len(relative.parts))]):
        try:
            info = component.lstat()
        except OSError as exc:
            raise ValueError("required CSV source is missing") from exc
        if (stat.S_ISLNK(info.st_mode) or
                bool(getattr(info, "st_file_attributes", 0) &
                     getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))):
            raise ValueError("linked/reparse CSV source refused")
    resolved = target.resolve(strict=True)
    if not resolved.is_relative_to(parent) or not resolved.is_file():
        raise ValueError("source must stay inside owner root as a regular file")
    return resolved


def validate_key_coverage_goal(raw: object, goal_file: Path) -> KeyCoverageGoal:
    fields = {"version", "kind", "goal", "master", "detail", "master_key",
              "detail_key", "encoding", "min_coverage_percent"}
    if (type(raw) is not dict or set(raw) != fields or
            type(raw["version"]) is not int or raw["version"] != 1 or
            raw["kind"] != "csv_key_coverage"):
        raise ValueError("invalid key coverage goal contract")
    title = raw["goal"]
    if (type(title) is not str or not 1 <= len(title.strip()) <= 120 or
            any(ord(x) < 32 for x in title)):
        raise ValueError("invalid key coverage goal title")
    for name in ("master_key", "detail_key"):
        key = raw[name]
        if (type(key) is not str or not 1 <= len(key) <= 60 or
                key != key.strip() or any(ord(x) < 32 for x in key)):
            raise ValueError("invalid key column")
    if (type(raw["encoding"]) is not str or
            raw["encoding"] not in ALLOWED_ENCODINGS):
        raise ValueError("unsupported CSV encoding")
    if type(raw["min_coverage_percent"]) is not str:
        raise ValueError("expected decimal text threshold")
    minimum = _num(raw["min_coverage_percent"], "min_coverage_percent")
    if minimum < 0 or minimum > 100:
        raise ValueError("min coverage must be 0..100")
    root = goal_file.parent.resolve(strict=True)
    master = _safe_owner_csv(root, raw["master"])
    detail = _safe_owner_csv(root, raw["detail"])
    if master == detail:
        raise ValueError("master and detail must be distinct local CSV files")
    return KeyCoverageGoal(title.strip(), master, detail, raw["master_key"],
                           raw["detail_key"], raw["encoding"], minimum)


def _read_keys(path: Path, column: str, encoding: str) -> tuple[dict, list[str]]:
    binary, digest = source_snapshot(path)
    old_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        stream = io.StringIO(binary.decode(encoding), newline="")
        reader = csv.reader(stream, strict=True)
        header = next(reader, None)
        if (header is None or not 1 <= len(header) <= MAX_COLUMNS or
                any(not 1 <= len(x) <= 60 or x != x.strip() or
                    any(ord(c) < 32 for c in x) for x in header) or
                len({x.casefold() for x in header}) != len(header) or
                column not in header):
            raise ValueError("invalid bounded CSV headers or missing key")
        index = header.index(column)
        keys = []
        for row in reader:
            if len(keys) >= MAX_ROWS or len(row) != len(header) or any(
                len(cell) > MAX_FIELD_CHARS for cell in row
            ):
                raise ValueError("CSV row count/width/cell limit exceeded")
            key = row[index].strip()
            if any(ord(c) < 32 or ord(c) == 127 for c in key):
                raise ValueError("source key contains unsupported control characters")
            keys.append(key)
    finally:
        csv.field_size_limit(old_limit)
    if source_snapshot(path)[1] != digest:
        raise ValueError("CSV source changed during key scan")
    return {"filename": path.name, "sha256": digest,
            "rows": len(keys), "key_column": column}, keys


def _pct(matched: int, count: int) -> str | None:
    if count == 0:
        return None
    with localcontext() as context:
        context.prec = 60
        return format((Decimal(matched) * 100 / Decimal(count)).quantize(
            Decimal("0.000001")), ".6f")


def execute_key_coverage_goal(goal: KeyCoverageGoal) -> dict:
    if type(goal) is not KeyCoverageGoal:
        raise ValueError("unvalidated key coverage goal")
    master, master_keys = _read_keys(goal.master, goal.master_key, goal.encoding)
    detail, detail_keys = _read_keys(goal.detail, goal.detail_key, goal.encoding)
    seen = set()
    duplicate = empty_master = 0
    for key in master_keys:
        if not key:
            empty_master += 1
        elif key in seen:
            duplicate += 1
        else:
            seen.add(key)
    empty_detail = matched = missing = 0
    for key in detail_keys:
        if not key:
            empty_detail += 1
        elif key in seen:
            matched += 1
        else:
            missing += 1
    checked = matched + missing
    coverage = _pct(matched, checked)
    # Use unrounded exact coverage for the policy gate; the six-decimal
    # percentage is display only and must never clear a borderline deficit.
    threshold_met = (None if checked == 0 else
                     Decimal(matched) * 100 >=
                     goal.min_coverage_percent * Decimal(checked))
    violation = bool(empty_master or duplicate or empty_detail or (
        threshold_met is False))
    status = ("CONFLICT" if violation else
              "UNAVAILABLE" if not master_keys or checked == 0 else "AGREE")
    if (source_snapshot(goal.master)[1] != master["sha256"] or
            source_snapshot(goal.detail)[1] != detail["sha256"]):
        raise ValueError("source changed during two-file key verification")
    return {
        "version": VERSION, "kind": "csv_key_coverage", "goal": goal.goal,
        "status": status, "master": master, "detail": detail,
        "master_duplicate_rows": duplicate, "master_empty_key_rows": empty_master,
        "detail_empty_key_rows": empty_detail, "detail_checked_rows": checked,
        "detail_matched_rows": matched, "detail_missing_reference_rows": missing,
        "coverage_percent": coverage,
        "min_coverage_percent": format(goal.min_coverage_percent, "f"),
        "coverage_threshold_met": threshold_met,
        "scope": SCOPE,
    }


def render_key_coverage(report: dict) -> str:
    return "\n".join((
        "EAI 오프라인 참조키 검수: " + report["status"],
        "마스터 중복 " + str(report["master_duplicate_rows"]) +
        "건 / 빈 키 " + str(report["master_empty_key_rows"]) + "건",
        "상세 미매칭 " + str(report["detail_missing_reference_rows"]) +
        "건 / 빈 키 " + str(report["detail_empty_key_rows"]) + "건",
        "검사대상 일치율 " + str(report["coverage_percent"]) +
        "% / 기준 " + report["min_coverage_percent"] + "%",
        report["scope"],
    ))
