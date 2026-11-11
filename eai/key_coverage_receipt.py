"""Independent column-oriented P31 CSV reference coverage verifier.

Deliberately does not call the P31 row-based solver. Regenerates every
source count, hash, coverage and final decision from bounded raw CSV bytes.
"""
from __future__ import annotations

from collections import Counter
import csv
from decimal import Decimal, localcontext
import io

from .csv_analysis import MAX_COLUMNS, MAX_ROWS, MAX_FIELD_CHARS
from .csv_quality import source_snapshot
from .csv_key_coverage import KeyCoverageGoal, VERSION, SCOPE


def _independent(path, column, encoding):
    data, digest = source_snapshot(path)
    old = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader = csv.DictReader(io.StringIO(data.decode(encoding), newline=""),
                                restkey="__overflow__", strict=True)
        names = reader.fieldnames
        if (type(names) is not list or not 1 <= len(names) <= MAX_COLUMNS or
                any(type(name) is not str or not 1 <= len(name) <= 60 or
                    name != name.strip() or any(ord(c) < 32 for c in name)
                    for name in names) or
                len({x.casefold() for x in names}) != len(names) or
                column not in names or "__overflow__" in names):
            raise ValueError("invalid independent CSV keys/header")
        keys = []
        for record in reader:
            if (len(keys) >= MAX_ROWS or "__overflow__" in record or
                    None in record or any(type(x) is not str or
                    len(x) > MAX_FIELD_CHARS for x in record.values())):
                raise ValueError("invalid independent CSV row")
            key = record[column].strip()
            if any(ord(c) < 32 or ord(c) == 127 for c in key):
                raise ValueError("independent key contains control characters")
            keys.append(key)
    finally:
        csv.field_size_limit(old)
    if source_snapshot(path)[1] != digest:
        raise ValueError("CSV source changed during independent scan")
    return {"filename": path.name, "sha256": digest, "rows": len(keys),
            "key_column": column}, keys


def verify_key_coverage_receipt(goal: KeyCoverageGoal, receipt: object):
    if type(goal) is not KeyCoverageGoal or type(receipt) is not dict:
        raise ValueError("invalid CSV key coverage verification inputs")
    parent, master_rows = _independent(goal.master, goal.master_key, goal.encoding)
    child, detail_rows = _independent(goal.detail, goal.detail_key, goal.encoding)
    counts = Counter(item for item in master_rows if item)
    empties = len(master_rows) - sum(counts.values())
    duplicates = sum(count - 1 for count in counts.values() if count > 1)
    empty_detail = sum(not k for k in detail_rows)
    matched = sum(bool(k) and k in counts for k in detail_rows)
    missing = sum(bool(k) and k not in counts for k in detail_rows)
    checked = matched + missing
    if checked:
        with localcontext() as ctx:
            ctx.prec = 60
            exact = Decimal(matched) * 100 / Decimal(checked)
            percent = format(exact.quantize(Decimal("0.000001")), ".6f")
            met = exact >= goal.min_coverage_percent
    else:
        percent, met = None, None
    violated = bool(duplicates or empties or empty_detail or met is False)
    status = ("CONFLICT" if violated else
              "UNAVAILABLE" if not master_rows or checked == 0 else "AGREE")
    expected = {
        "version": VERSION, "kind": "csv_key_coverage", "goal": goal.goal,
        "status": status, "master": parent, "detail": child,
        "master_duplicate_rows": duplicates, "master_empty_key_rows": empties,
        "detail_empty_key_rows": empty_detail, "detail_checked_rows": checked,
        "detail_matched_rows": matched, "detail_missing_reference_rows": missing,
        "coverage_percent": percent,
        "min_coverage_percent": format(goal.min_coverage_percent, "f"),
        "coverage_threshold_met": met, "scope": SCOPE,
    }
    if expected != receipt:
        raise ValueError("EAI key coverage receipt independently disagrees")
    diag = (
        {"type": "RELATIONAL_INTEGRITY_REVIEW", "action_required": True,
         "hint": "참조 누락·중복·빈 키·허용 일치율을 소유자 원본에서 확인하세요."}
        if status == "CONFLICT" else
        {"type": "REFERENCE_COVERAGE_UNKNOWN", "action_required": True,
         "hint": "마스터/상세 유효 키가 없어 일치율 검증이 불가능합니다."}
        if status == "UNAVAILABLE" else
        {"type": "NONE", "action_required": False}
    )
    return (["source_sha256", "strict_csv_rows", "independent_counter",
             "reference_coverage", "threshold", "status"], diag)
