"""P18 separate, column-first source audit to reject altered SQLite receipts."""
from collections import Counter

from .sqlite_table_audit import (
    SqliteTableGoal, VERSION, SCOPE, MAX_SAMPLES, source_digest,
    _connect_and_read, is_blank
)


def verify_sqlite_receipt(goal: SqliteTableGoal, report: object) -> tuple[list[str], dict]:
    if type(goal) is not SqliteTableGoal or type(report) is not dict:
        raise ValueError("EAI SQLite receipt invalid")
    before = source_digest(goal.source)
    columns, rows = _connect_and_read(goal)
    positions = {name: n for n, name in enumerate(columns)}
    # Reconstruct missing data by columns, instead of trusting the row-first solver.
    missing = {
        name: {i for i, row in enumerate(rows, 1) if is_blank(row[positions[name]])}
        for name in goal.required
    }
    keys = [
        tuple(row[positions[name]] for name in goal.unique_by) for row in rows
    ]
    present = [not any(is_blank(v) for v in key) for key in keys]
    frequencies = Counter(key for key, ok in zip(keys, present) if ok)
    seen = set()
    duplicate_indices = set()
    for i, (key, ok) in enumerate(zip(keys, present), 1):
        if ok:
            if key in seen:
                duplicate_indices.add(i)
            seen.add(key)
    # Frequencies are checked separately from the record-index reconstruction.
    duplicate_count = sum(count - 1 for count in frequencies.values())
    if duplicate_count != len(duplicate_indices):
        raise ValueError("EAI SQLite duplicate evidence inconsistency")
    events = []
    for i in range(1, len(rows) + 1):
        for name in goal.required:
            if i in missing[name]:
                events.append({"record": i, "code": "MISSING_REQUIRED", "column": name})
        if i in duplicate_indices:
            events.append({
                "record": i, "code": "DUPLICATE_KEY",
                "column": ",".join(goal.unique_by)
            })
    counts = {
        "MISSING_REQUIRED": sum(len(ids) for ids in missing.values()),
        "DUPLICATE_KEY": duplicate_count
    }
    if source_digest(goal.source) != before:
        raise ValueError("SQLite file changed during independent receipt check")
    expected_status = "UNAVAILABLE" if not rows else (
        "CONFLICT" if any(counts.values()) else "AGREE"
    )
    expected = {
        "version": VERSION, "kind": "sqlite_table_audit", "goal": goal.goal,
        "filename": goal.source.name, "sha256": before,
        "table": goal.table, "columns": columns,
        "required": list(goal.required), "unique_by": list(goal.unique_by),
        "status": expected_status, "rows": len(rows), "counts": counts,
        "affected_records": len({event["record"] for event in events}),
        "samples": events[:MAX_SAMPLES], "scope": SCOPE
    }
    if report != expected:
        raise ValueError("EAI SQLite receipt verification failed: forged source or evidence")
    diagnostic = (
        {"type": "SQLITE_INTEGRITY_REVIEW", "action_required": True,
         "hint": "필수 열 누락값과 반복 키의 로컬 레코드 인덱스를 검토하세요."}
        if expected_status == "CONFLICT" else
        {"type": "SQLITE_EMPTY", "action_required": True,
         "hint": "데이터 행이 없어 무결성 검사를 확정할 수 없습니다."}
        if expected_status == "UNAVAILABLE" else
        {"type": "NONE", "action_required": False}
    )
    return (
        ["sqlite_sha256", "table_schema", "column_nulls",
         "composite_key_frequency", "samples", "status"], diagnostic
    )
