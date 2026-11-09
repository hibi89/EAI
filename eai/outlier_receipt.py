"""P22 independent column-oriented MAD verifier over raw CSV bytes."""
from decimal import Decimal, localcontext
import csv
import io
import statistics

from .analysis import _NUMBER, _render_decimal
from .csv_analysis import MAX_ROWS, MAX_COLUMNS, MAX_FIELD_CHARS
from .csv_quality import source_snapshot
from .csv_robust_outliers import OutlierGoal, VERSION, SCOPE


def verify_outlier_receipt(goal: OutlierGoal, report: object) -> tuple[list[str], dict]:
    if type(goal) is not OutlierGoal or type(report) is not dict:
        raise ValueError("outlier receipt must have validated input/report")
    binary, digest = source_snapshot(goal.source)
    old = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader = csv.DictReader(
            io.StringIO(binary.decode(goal.encoding), newline=""), strict=True
        )
        headers = reader.fieldnames
        if type(headers) is not list or not 1 <= len(headers) <= MAX_COLUMNS or any(
            not 1 <= len(h) <= 60 or h != h.strip() or
            any(ord(ch) < 32 for ch in h) for h in headers
        ) or len({h.casefold() for h in headers}) != len(headers):
            raise ValueError("outlier receipt malformed CSV header")
        if not set(goal.columns) <= set(headers):
            raise ValueError("outlier receipt references absent columns")
        rows, missing, invalid = 0, 0, 0
        values = {name: [] for name in goal.columns}
        indices = []
        for row in reader:
            rows += 1
            if rows > MAX_ROWS or None in row or any(
                type(cell) is not str or len(cell) > MAX_FIELD_CHARS
                for cell in row.values()
            ):
                raise ValueError("outlier receipt malformed source row")
            selected = [row[name].strip() for name in goal.columns]
            if any(cell and not _NUMBER.fullmatch(cell) for cell in selected):
                invalid += 1
            elif not all(selected):
                missing += 1
            else:
                indices.append(rows)
                for name, cell in zip(goal.columns, selected):
                    values[name].append(Decimal(cell))
        n = len(indices)
        profiles, samples = [], []
        with localcontext() as ctx:
            ctx.prec = 110
            for name in goal.columns:
                if n < goal.min_rows:
                    profiles.append({"column": name, "median": None, "mad": None,
                                     "estimable": False, "outliers": 0})
                    continue
                series = values[name]
                center = statistics.median(series)
                spread = statistics.median([abs(x - center) for x in series])
                flagged = []
                if spread > 0:
                    for line, value in zip(indices, series):
                        # Independent test uses exact multiplication instead of
                        # the solver's ratio division.
                        if abs(value - center) > goal.threshold * spread:
                            flagged.append(line)
                profiles.append({
                    "column": name, "median": _render_decimal(center),
                    "mad": _render_decimal(spread),
                    "estimable": spread > 0, "outliers": len(flagged)
                })
                for index in flagged:
                    if len(samples) < 10:
                        samples.append({"record": index, "column": name})
    finally:
        csv.field_size_limit(old)
    if source_snapshot(goal.source)[1] != digest:
        raise ValueError("outlier receipt source changed during check")
    status = (
        "CONFLICT" if missing or invalid or any(p["outliers"] for p in profiles)
        else "UNAVAILABLE" if any(not p["estimable"] for p in profiles)
        else "AGREE"
    )
    expected = {
        "version": VERSION, "kind": "csv_robust_outliers",
        "goal": goal.goal, "status": status, "filename": goal.source.name,
        "sha256": digest, "encoding": goal.encoding, "columns": list(goal.columns),
        "min_rows": goal.min_rows, "threshold": _render_decimal(goal.threshold),
        "rows": rows, "complete_rows": n,
        "missing_rows": missing, "invalid_rows": invalid,
        "profiles": profiles, "samples": samples, "scope": SCOPE
    }
    if expected != report:
        raise ValueError("outlier receipt failed: forged or inconsistent source evidence")
    diagnostic = (
        {"type": "OUTLIER_OR_INPUT_REVIEW", "action_required": True,
         "hint": "원본의 이상후보 순번과 결측/비숫자 수치를 검토하세요."}
        if status == "CONFLICT" else
        {"type": "INSUFFICIENT_ROBUST_SCALE", "action_required": True,
         "hint": "표본 부족이나 MAD=0 열은 강건 이상점수를 계산할 수 없습니다."}
        if status == "UNAVAILABLE" else
        {"type": "NONE", "action_required": False}
    )
    return [
        "source_sha256", "complete_case_counts", "independent_median",
        "independent_mad", "threshold_flags", "status"
    ], diagnostic
