"""P22 CPU-only robust median absolute deviation outlier discovery on local CSV."""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import csv
import io
from pathlib import Path

from .analysis import _NUMBER, _render_decimal
from .decision_engine import _num
from .csv_analysis import MAX_COLUMNS, MAX_ROWS, MAX_FIELD_CHARS, ALLOWED_ENCODINGS
from .csv_quality import source_snapshot

VERSION = "eai.goal.csv_robust_outliers.v1"
SCOPE = (
    "로컬 CSV에서 중앙값·MAD 기반의 이상치 후보를 통계적으로 탐지했습니다. "
    "이는 오류·사기·인과관계의 증거가 아닙니다. MAD=0 또는 표본 부족은 "
    "추정 불가로 표시하며, 자동 데이터 삭제·수정·전송을 하지 않습니다. "
    "원본 셀값·고유 키는 출력하지 않고 집계값·레코드 순번만 제공합니다."
)


@dataclass(frozen=True)
class OutlierGoal:
    goal: str
    source: Path
    encoding: str
    columns: tuple[str, ...]
    min_rows: int
    threshold: Decimal


def validate_outlier_goal(raw: object, spec_path: Path) -> OutlierGoal:
    fields = {"version", "kind", "goal", "source", "encoding", "columns",
              "min_rows", "threshold"}
    if type(raw) is not dict or set(raw) != fields or (
        type(raw["version"]) is not int or raw["version"] != 1 or
        raw["kind"] != "csv_robust_outliers"
    ):
        raise ValueError("invalid versioned csv_robust_outliers contract")
    title = raw["goal"]
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(
        ord(c) < 32 for c in title
    ):
        raise ValueError("invalid outlier goal title")
    value = raw["source"]
    if type(value) is not str or not 1 <= len(value) <= 512 or any(
        ch in "\\:" or ord(ch) < 32 for ch in value
    ):
        raise ValueError("outlier CSV must be a local relative filename")
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("outlier path escapes owner goal directory")
    root = spec_path.parent.resolve(strict=True)
    source = (root / rel).resolve(strict=True)
    if not source.is_relative_to(root):
        raise ValueError("outlier symlink path escapes owner directory")
    encoding = raw["encoding"]
    if type(encoding) is not str or encoding not in ALLOWED_ENCODINGS:
        raise ValueError("unsupported outlier encoding")
    cols = raw["columns"]
    if type(cols) is not list or not 1 <= len(cols) <= 4 or any(
        type(c) is not str or not 1 <= len(c) <= 60 or c != c.strip() or
        any(ord(ch) < 32 for ch in c) for c in cols
    ) or len({c.casefold() for c in cols}) != len(cols):
        raise ValueError("outliers require 1-4 distinct numeric columns")
    min_rows = raw["min_rows"]
    if type(min_rows) is not int or not 5 <= min_rows <= MAX_ROWS:
        raise ValueError("min_rows must be integer 5..20000")
    threshold = _num(raw["threshold"], "outlier.threshold")
    if not Decimal("1") <= threshold <= Decimal("20"):
        raise ValueError("outlier threshold must be between 1 and 20")
    return OutlierGoal(title.strip(), source, encoding, tuple(cols),
                       min_rows, threshold)


def median(values: list[Decimal]) -> Decimal:
    sorted_values = sorted(values)
    length = len(sorted_values)
    if not length:
        raise ValueError("median requires observations")
    mid = length // 2
    return (sorted_values[mid] if length % 2
            else (sorted_values[mid - 1] + sorted_values[mid]) / 2)


def _read_selected(goal: OutlierGoal):
    binary, digest = source_snapshot(goal.source)
    old = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        source = csv.reader(io.StringIO(binary.decode(goal.encoding), newline=""),
                            strict=True)
        try:
            headers = next(source)
        except StopIteration as exc:
            raise ValueError("outlier CSV has no header") from exc
        if not 1 <= len(headers) <= MAX_COLUMNS or any(
            not 1 <= len(x) <= 60 or x != x.strip() or
            any(ord(ch) < 32 for ch in x) for x in headers
        ) or len({x.casefold() for x in headers}) != len(headers):
            raise ValueError("outlier CSV has invalid/duplicate columns")
        positions = {h: i for i, h in enumerate(headers)}
        if not set(goal.columns) <= set(positions):
            raise ValueError("unknown outlier target column")
        valid, rows, missing, invalid = [], 0, 0, 0
        for cells in source:
            rows += 1
            if rows > MAX_ROWS or len(cells) != len(headers) or any(
                len(cell) > MAX_FIELD_CHARS for cell in cells
            ):
                raise ValueError("outlier CSV row/field limit exceeded")
            selected = [cells[positions[h]].strip() for h in goal.columns]
            if any(cell and not _NUMBER.fullmatch(cell) for cell in selected):
                invalid += 1
            elif not all(selected):
                missing += 1
            else:
                valid.append((rows, tuple(Decimal(cell) for cell in selected)))
    finally:
        csv.field_size_limit(old)
    if source_snapshot(goal.source)[1] != digest:
        raise ValueError("outlier CSV changed during scan")
    return digest, rows, missing, invalid, valid


def execute_outlier_goal(goal: OutlierGoal) -> dict:
    if type(goal) is not OutlierGoal:
        raise ValueError("invalid outlier goal instance")
    digest, rows, missing, invalid, valid = _read_selected(goal)
    profiles = []
    flags = []
    with localcontext() as ctx:
        ctx.prec = 110
        if len(valid) >= goal.min_rows:
            for col_no, column in enumerate(goal.columns):
                values = [v[col_no] for _, v in valid]
                center = median(values)
                spread = median([abs(v - center) for v in values])
                count = 0
                if spread > 0:
                    for index, value in valid:
                        if abs(value - center) / spread > goal.threshold:
                            count += 1
                            if len(flags) < 10:
                                flags.append({"record": index, "column": column})
                profiles.append({
                    "column": column, "median": _render_decimal(center),
                    "mad": _render_decimal(spread),
                    "estimable": spread > 0, "outliers": count
                })
        else:
            profiles = [{"column": name, "median": None, "mad": None,
                         "estimable": False, "outliers": 0}
                        for name in goal.columns]
    # Samples order is defined as (selected column order, original record order).
    status = ("CONFLICT" if missing or invalid or any(x["outliers"] for x in profiles)
              else "UNAVAILABLE" if any(not x["estimable"] for x in profiles)
              else "AGREE")
    return {
        "version": VERSION, "kind": "csv_robust_outliers",
        "goal": goal.goal, "status": status, "filename": goal.source.name,
        "sha256": digest, "encoding": goal.encoding, "columns": list(goal.columns),
        "min_rows": goal.min_rows, "threshold": _render_decimal(goal.threshold),
        "rows": rows, "complete_rows": len(valid),
        "missing_rows": missing, "invalid_rows": invalid,
        "profiles": profiles, "samples": flags, "scope": SCOPE
    }


def render_outliers(report: dict) -> str:
    lines = ["EAI CPU 강건 이상치 탐색: " + report["status"],
             f"원본 SHA256: {report['sha256']}",
             f"전체 {report['rows']} / 유효 {report['complete_rows']} / "
             f"결측 {report['missing_rows']} / 비숫자 {report['invalid_rows']}"]
    for item in report["profiles"]:
        lines.append(f"{item['column']}: median={item['median']}, "
                     f"MAD={item['mad']}, 이상후보 {item['outliers']}")
    for hit in report["samples"]:
        lines.append(f"레코드 {hit['record']}: {hit['column']} 이상 후보")
    return "\n".join(lines + [report["scope"]])
