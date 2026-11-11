"""P29 bounded two-cohort median/MAD distribution shift, local CPU only."""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import csv
import io
from pathlib import Path

from .analysis import _NUMBER
from .decision_engine import _num
from .csv_analysis import ALLOWED_ENCODINGS, MAX_COLUMNS, MAX_ROWS, MAX_FIELD_CHARS
from .csv_quality import source_snapshot

VERSION = "eai.goal.csv_distribution_shift.v1"
SCOPE = (
    "소유자가 선택한 두 CSV의 중앙값 이동을 기준 자료 MAD 단위로 비교합니다. "
    "두 집단의 시간적·표본적 대표성, 인과성, 통계적 유의성은 확인하지 않습니다. "
    "MAD=0이나 표본 부족은 추정불가이고 결측/비숫자는 충돌로 표시합니다. "
    "원본 셀값은 출력하지 않고 파일 수정·자동 대응·외부 전송은 수행하지 않습니다."
)


@dataclass(frozen=True)
class ShiftGoal:
    goal: str
    baseline: Path
    current: Path
    encoding: str
    columns: tuple[str, ...]
    min_rows: int
    threshold: Decimal


def validate_shift_goal(raw: object, goal_file: Path) -> ShiftGoal:
    fields = {"version","kind","goal","baseline","current","encoding",
              "columns","min_rows","threshold"}
    if type(raw) is not dict or set(raw) != fields or (
        type(raw["version"]) is not int or raw["version"] != 1 or
        raw["kind"] != "csv_distribution_shift"
    ):
        raise ValueError("invalid distribution shift goal contract")
    title = raw["goal"]
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(
        ord(c) < 32 for c in title
    ):
        raise ValueError("invalid shift goal title")
    base = goal_file.parent.resolve(strict=True)
    def selected_path(value):
        if type(value) is not str or not 1 <= len(value) <= 512 or any(
            c in "\\:" or ord(c) < 32 for c in value
        ):
            raise ValueError("invalid source path")
        loc = Path(value)
        if loc.is_absolute() or ".." in loc.parts or loc.suffix.lower() != ".csv":
            raise ValueError("only in-root relative CSV files are permitted")
        result = (base / loc).resolve(strict=True)
        if not result.is_relative_to(base) or result.suffix.lower() != ".csv":
            raise ValueError("source symlink escapes owner root")
        return result
    baseline = selected_path(raw["baseline"])
    current = selected_path(raw["current"])
    if baseline == current or baseline.name == current.name:
        raise ValueError("two distinct unambiguous source files required")
    cols = raw["columns"]
    if type(cols) is not list or not 1 <= len(cols) <= 4 or any(
        type(c) is not str or not 1 <= len(c) <= 60 or c != c.strip() or
        any(ord(x) < 32 for x in c) for c in cols
    ) or len({c.casefold() for c in cols}) != len(cols):
        raise ValueError("shift requires 1-4 distinct column names")
    if type(raw["encoding"]) is not str or raw["encoding"] not in ALLOWED_ENCODINGS:
        raise ValueError("unsupported encoding")
    if type(raw["min_rows"]) is not int or not 5 <= raw["min_rows"] <= MAX_ROWS:
        raise ValueError("min_rows must be an integer from 5 to 20000")
    threshold = _num(raw["threshold"], "shift.threshold")
    if not Decimal("0.5") <= threshold <= Decimal("20"):
        raise ValueError("shift threshold must be 0.5..20 MAD units")
    return ShiftGoal(title.strip(), baseline, current, raw["encoding"],
                     tuple(cols), raw["min_rows"], threshold)


def _read_rows(path: Path, goal: ShiftGoal):
    binary, digest = source_snapshot(path)
    old = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader = csv.reader(io.StringIO(binary.decode(goal.encoding), newline=""), strict=True)
        headers = next(reader, None)
        if headers is None or not 1 <= len(headers) <= MAX_COLUMNS or any(
            not 1 <= len(h) <= 60 or h != h.strip() or any(ord(c) < 32 for c in h)
            for h in headers
        ) or len({h.casefold() for h in headers}) != len(headers):
            raise ValueError("invalid shift source headers")
        index = {h:i for i,h in enumerate(headers)}
        if not set(goal.columns) <= set(index):
            raise ValueError("selected numeric column missing from source")
        data, seen, invalid = [], 0, 0
        for row in reader:
            seen += 1
            if seen > MAX_ROWS or len(row) != len(headers) or any(
                len(x) > MAX_FIELD_CHARS for x in row
            ):
                raise ValueError("source row width/count/cell bound exceeded")
            cells = [row[index[name]].strip() for name in goal.columns]
            if any(not x or not _NUMBER.fullmatch(x) for x in cells):
                invalid += 1
            else:
                data.append(tuple(Decimal(x) for x in cells))
    finally:
        csv.field_size_limit(old)
    if source_snapshot(path)[1] != digest:
        raise ValueError("shift source changed during scan")
    return {
        "filename":path.name,"sha256":digest,"rows":seen,
        "complete_rows":len(data),"invalid_rows":invalid,
    }, data


def _median(values: list[Decimal]) -> Decimal:
    values = sorted(values)
    middle = len(values)//2
    return (values[middle] if len(values)%2 else
            (values[middle-1]+values[middle])/2)


def _quant(number: Decimal) -> str:
    return format(number.quantize(Decimal("0.000001")), "f")


def execute_shift_goal(goal: ShiftGoal) -> dict:
    if type(goal) is not ShiftGoal:
        raise ValueError("unvalidated shift goal")
    old_meta, first = _read_rows(goal.baseline, goal)
    new_meta, second = _read_rows(goal.current, goal)
    reports, any_shift, unavailable = [], False, False
    with localcontext() as ctx:
        ctx.prec = 110
        for index, name in enumerate(goal.columns):
            if len(first) < goal.min_rows or len(second) < goal.min_rows:
                row = {"column":name,"baseline_median":None,"current_median":None,
                       "baseline_mad":None,"shift_mad_units":None,"state":"NOT_ESTIMABLE"}
                unavailable = True
            else:
                baseline = [row[index] for row in first]
                recent = [row[index] for row in second]
                med0, med1 = _median(baseline),_median(recent)
                mad = _median([abs(v-med0) for v in baseline])
                if mad == 0:
                    units, state = None,"NOT_ESTIMABLE"
                    unavailable = True
                else:
                    units = _quant(abs(med1-med0)/mad)
                    state = ("SHIFT" if Decimal(units) > goal.threshold else "STABLE")
                    any_shift |= state == "SHIFT"
                row = {"column":name,"baseline_median":format(med0,"f"),
                       "current_median":format(med1,"f"),
                       "baseline_mad":format(mad,"f"),
                       "shift_mad_units":units,"state":state}
            reports.append(row)
    if source_snapshot(goal.baseline)[1] != old_meta["sha256"] or (
        source_snapshot(goal.current)[1] != new_meta["sha256"]
    ):
        raise ValueError("source changed across shift scans")
    status = ("CONFLICT" if any_shift or old_meta["invalid_rows"] or new_meta["invalid_rows"]
              else "UNAVAILABLE" if unavailable else "AGREE")
    return {
        "version":VERSION,"kind":"csv_distribution_shift","goal":goal.goal,
        "status":status,"threshold":format(goal.threshold,"f"),
        "sources":[old_meta,new_meta],"columns":reports,"scope":SCOPE,
    }


def render_shift(report: dict) -> str:
    lines = ["EAI 로컬 CSV 분포 변화: " + report["status"]]
    for column in report["columns"]:
        lines.append(f"{column['column']}: {column['state']} / "
                     f"MAD units={column['shift_mad_units']}")
    lines.append(report["scope"])
    return "\n".join(lines)
