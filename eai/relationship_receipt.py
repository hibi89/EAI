"""P19 independent raw-moment verifier over csv.DictReader, no solver reuse."""
import csv
from decimal import Decimal, localcontext
import io
from itertools import combinations

from .analysis import _NUMBER
from .csv_analysis import MAX_ROWS, MAX_COLUMNS, MAX_FIELD_CHARS
from .csv_quality import source_snapshot
from .csv_relationships import RelationshipGoal, VERSION, SCOPE


def _direction(value: Decimal | None) -> str:
    if value is None:
        return "NOT_ESTIMABLE"
    if value >= Decimal("0.7"):
        return "STRONG_POSITIVE"
    if value <= Decimal("-0.7"):
        return "STRONG_NEGATIVE"
    if value >= Decimal("0.3"):
        return "MODERATE_POSITIVE"
    if value <= Decimal("-0.3"):
        return "MODERATE_NEGATIVE"
    return "WEAK_OR_NONE"


def verify_relationship_receipt(goal: RelationshipGoal, report: object) -> tuple[list[str], dict]:
    if type(goal) is not RelationshipGoal or type(report) is not dict:
        raise ValueError("EAI relationship receipt invalid contract")
    data, digest = source_snapshot(goal.source)
    old = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader = csv.DictReader(io.StringIO(data.decode(goal.encoding), newline=""),
                                strict=True)
        headers = reader.fieldnames
        if type(headers) is not list or not 1 <= len(headers) <= MAX_COLUMNS or any(
            not 1 <= len(header) <= 60 or header != header.strip() or
            any(ord(c) < 32 for c in header) for header in headers
        ) or len({h.casefold() for h in headers}) != len(headers):
            raise ValueError("relationship receipt malformed headers")
        if not set(goal.columns) <= set(headers):
            raise ValueError("relationship receipt missing numeric columns")
        rows = missing = invalid = 0
        count = len(goal.columns)
        with localcontext() as ctx:
            ctx.prec = 110
            sums = [Decimal(0)] * count
            cross = [[Decimal(0) for _ in range(count)] for _ in range(count)]
            n = 0
            for record in reader:
                rows += 1
                if rows > MAX_ROWS or None in record or any(
                    type(v) is not str or len(v) > MAX_FIELD_CHARS
                    for v in record.values()
                ):
                    raise ValueError("relationship receipt malformed row")
                vals = [record[c].strip() for c in goal.columns]
                if any(v and not _NUMBER.fullmatch(v) for v in vals):
                    invalid += 1
                elif not all(vals):
                    missing += 1
                else:
                    numbers = [Decimal(v) for v in vals]
                    n += 1
                    for i, a in enumerate(numbers):
                        sums[i] += a
                        for j, b in enumerate(numbers):
                            cross[i][j] += a * b
            pairs = []
            for i, j in combinations(range(count), 2):
                coefficient = None
                if n >= goal.min_rows:
                    left = n * cross[i][i] - sums[i] * sums[i]
                    right = n * cross[j][j] - sums[j] * sums[j]
                    if left > 0 and right > 0:
                        covariance = n * cross[i][j] - sums[i] * sums[j]
                        val = covariance / (left * right).sqrt()
                        val = max(Decimal("-1"), min(Decimal("1"), val))
                        coefficient = val.quantize(Decimal("0.000001"))
                pairs.append({
                    "left": goal.columns[i], "right": goal.columns[j],
                    "coefficient": None if coefficient is None else format(coefficient, ".6f"),
                    "direction": _direction(coefficient)
                })
    finally:
        csv.field_size_limit(old)
    if source_snapshot(goal.source)[1] != digest:
        raise ValueError("relationship source changed during verification")
    status = (
        "CONFLICT" if (missing or invalid) else
        "UNAVAILABLE" if any(p["coefficient"] is None for p in pairs) else "AGREE"
    )
    expected = {
        "version": VERSION, "kind": "csv_relationships", "goal": goal.goal,
        "status": status, "filename": goal.source.name, "sha256": digest,
        "encoding": goal.encoding, "columns": list(goal.columns),
        "min_rows": goal.min_rows, "rows": rows, "complete_rows": n,
        "missing_rows": missing, "invalid_rows": invalid, "pairs": pairs,
        "scope": SCOPE
    }
    if expected != report:
        raise ValueError("EAI relationship receipt verification failed: forged/inconsistent")
    diag = (
        {"type": "NUMERIC_DATA_REVIEW", "action_required": True,
         "hint": "빈 값과 비숫자 입력을 원본에서 확인하세요. 임의 대체하지 않았습니다."}
        if status == "CONFLICT" else
        {"type": "INSUFFICIENT_VARIATION", "action_required": True,
         "hint": "최소 관측수/상수 열을 검토하세요. 상관계수를 추정할 수 없습니다."}
        if status == "UNAVAILABLE" else
        {"type": "NONE", "action_required": False}
    )
    return (
        ["sha256", "selected_columns", "row_classification",
         "raw_second_moments", "pairwise_correlations", "status"], diag
    )
