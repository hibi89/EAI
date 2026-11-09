"""P19 bounded numeric association discovery over owner-selected local CSV."""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import csv
import io
from itertools import combinations
from pathlib import Path

from .analysis import _NUMBER
from .csv_analysis import (
    ALLOWED_ENCODINGS, MAX_ROWS, MAX_COLUMNS, MAX_FIELD_CHARS
)
from .csv_quality import source_snapshot

VERSION = "eai.goal.csv_relationships.v1"
SCOPE = (
    "지정된 로컬 CSV 숫자 열의 완전 관측행 기준 Pearson 상관계수만 CPU로 계산했습니다. "
    "결측/비숫자 입력은 누락 행으로 자동 대체하지 않고 별도 충돌로 표시합니다. "
    "상관관계는 인과관계·예측력·통계적 유의성의 증거가 아닙니다. "
    "원본값·개별 행·식별자는 출력하지 않으며 파일 수정·외부 호출은 없습니다."
)
QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class RelationshipGoal:
    goal: str
    source: Path
    encoding: str
    columns: tuple[str, ...]
    min_rows: int


def validate_relationship_goal(raw: object, spec_file: Path) -> RelationshipGoal:
    fields = {"version", "kind", "goal", "source", "encoding", "columns", "min_rows"}
    if type(raw) is not dict or set(raw) != fields or (
        type(raw["version"]) is not int or raw["version"] != 1 or
        raw["kind"] != "csv_relationships"
    ):
        raise ValueError("invalid csv_relationships versioned contract")
    title = raw["goal"]
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(
        ord(ch) < 32 for ch in title
    ):
        raise ValueError("invalid relationship goal title")
    path = raw["source"]
    if type(path) is not str or not 1 <= len(path) <= 512 or any(
        ch in "\\:" or ord(ch) < 32 for ch in path
    ):
        raise ValueError("relationship source must be a relative local path")
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("relationship source path escapes folder")
    base = spec_file.parent.resolve(strict=True)
    source = (base / relative).resolve(strict=True)
    if not source.is_relative_to(base):
        raise ValueError("relationship symlink escapes folder")
    encoding = raw["encoding"]
    if type(encoding) is not str or encoding not in ALLOWED_ENCODINGS:
        raise ValueError("invalid relationship source encoding")
    cols = raw["columns"]
    if type(cols) is not list or not 2 <= len(cols) <= 6 or any(
        type(x) is not str or not 1 <= len(x) <= 60 or x != x.strip() or
        any(ord(ch) < 32 for ch in x) for x in cols
    ) or len({x.casefold() for x in cols}) != len(cols):
        raise ValueError("relationship columns require 2-6 distinct headers")
    min_rows = raw["min_rows"]
    if type(min_rows) is not int or not 5 <= min_rows <= MAX_ROWS:
        raise ValueError("relationship min_rows must be an integer from 5 to 20000")
    return RelationshipGoal(title.strip(), source, encoding, tuple(cols), min_rows)


def _relation(score: Decimal | None) -> str:
    if score is None:
        return "NOT_ESTIMABLE"
    if score >= Decimal("0.7"):
        return "STRONG_POSITIVE"
    if score <= Decimal("-0.7"):
        return "STRONG_NEGATIVE"
    if score >= Decimal("0.3"):
        return "MODERATE_POSITIVE"
    if score <= Decimal("-0.3"):
        return "MODERATE_NEGATIVE"
    return "WEAK_OR_NONE"


def _parse(goal: RelationshipGoal) -> tuple[str, int, int, int, list[tuple[Decimal, ...]]]:
    """Strict csv.reader scan; only selected complete rows are retained in memory."""
    raw, sha = source_snapshot(goal.source)
    old = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader = csv.reader(io.StringIO(raw.decode(goal.encoding), newline=""), strict=True)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise ValueError("relationship CSV missing headers") from exc
        if not 1 <= len(headers) <= MAX_COLUMNS or any(
            not 1 <= len(x) <= 60 or x != x.strip() or
            any(ord(c) < 32 for c in x) for x in headers
        ) or len({x.casefold() for x in headers}) != len(headers):
            raise ValueError("invalid relationship CSV header")
        pos = {name: index for index, name in enumerate(headers)}
        if not set(goal.columns) <= set(pos):
            raise ValueError("relationship goal refers to unknown numeric column")
        complete = []
        records = missing = invalid = 0
        for row in reader:
            records += 1
            if records > MAX_ROWS or len(row) != len(headers) or any(
                len(cell) > MAX_FIELD_CHARS for cell in row
            ):
                raise ValueError("relationship source row/column bound exceeded")
            raw_values = [row[pos[name]].strip() for name in goal.columns]
            if any(value and not _NUMBER.fullmatch(value) for value in raw_values):
                invalid += 1
            elif not all(raw_values):
                missing += 1
            else:
                complete.append(tuple(Decimal(value) for value in raw_values))
    finally:
        csv.field_size_limit(old)
    if source_snapshot(goal.source)[1] != sha:
        raise ValueError("relationship source changed during scan")
    return sha, records, missing, invalid, complete


def execute_relationship_goal(goal: RelationshipGoal) -> dict:
    if type(goal) is not RelationshipGoal:
        raise ValueError("unvalidated relationship goal")
    sha, records, missing, invalid, observations = _parse(goal)
    n = len(observations)
    pairs = []
    with localcontext() as ctx:
        ctx.prec = 110
        means = [
            sum((row[i] for row in observations), Decimal(0)) / n
            for i in range(len(goal.columns))
        ] if n >= goal.min_rows else []
        centered = [
            tuple(value - means[i] for i, value in enumerate(row))
            for row in observations
        ] if means else []
        variance = [
            sum((row[i] * row[i] for row in centered), Decimal(0))
            for i in range(len(goal.columns))
        ] if centered else []
        for i, j in combinations(range(len(goal.columns)), 2):
            coefficient = None
            if n >= goal.min_rows and variance[i] > 0 and variance[j] > 0:
                cov = sum((row[i] * row[j] for row in centered), Decimal(0))
                r = cov / (variance[i] * variance[j]).sqrt()
                r = max(Decimal("-1"), min(Decimal("1"), r))
                coefficient = r.quantize(QUANT)
            pairs.append({
                "left": goal.columns[i], "right": goal.columns[j],
                "coefficient": None if coefficient is None else format(coefficient, ".6f"),
                "direction": _relation(coefficient)
            })
    status = (
        "CONFLICT" if (missing or invalid) else
        "UNAVAILABLE" if any(pair["coefficient"] is None for pair in pairs) else
        "AGREE"
    )
    return {
        "version": VERSION, "kind": "csv_relationships", "goal": goal.goal,
        "status": status, "filename": goal.source.name, "sha256": sha,
        "encoding": goal.encoding, "columns": list(goal.columns),
        "min_rows": goal.min_rows, "rows": records, "complete_rows": n,
        "missing_rows": missing, "invalid_rows": invalid, "pairs": pairs,
        "scope": SCOPE
    }


def render_relationships(report: dict) -> str:
    lines = [
        "EAI CPU 다변량 관계 분석: " + report["status"],
        "원본: " + report["filename"] + " SHA256 " + report["sha256"],
        f"전체 {report['rows']} / 유효 {report['complete_rows']} / "
        f"결측 {report['missing_rows']} / 비숫자 {report['invalid_rows']}"
    ]
    for pair in report["pairs"]:
        lines.append(
            pair["left"] + " ↔ " + pair["right"] + ": " +
            str(pair["coefficient"]) + " / " + pair["direction"]
        )
    return "\n".join(lines + [report["scope"]])
