"""P18: bounded, evidence-only audit of one explicitly selected local SQLite table."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import sqlite3
import time

VERSION = "eai.goal.sqlite_table_audit.v1"
MAX_DB_BYTES = 16 * 1024 * 1024
MAX_ROWS = 20000
MAX_COLS = 32
MAX_SAMPLES = 10
IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,63}\Z")
CODES = ("MISSING_REQUIRED", "DUPLICATE_KEY")
SCOPE = (
    "지정된 단일 SQLite 일반 테이블의 필수값 누락과 반복 키만 검사했습니다. "
    "값, 키 및 레코드 원문은 표시하지 않습니다. 로컬 원본은 읽기 전용이며 "
    "임의 SQL, 외부 연결, 자동 복구, 인과 추론을 수행하지 않습니다. "
    "활성 WAL/저널 DB, 가상 테이블, 뷰 및 사용자 정의 collation은 지원하지 않습니다."
)


@dataclass(frozen=True)
class SqliteTableGoal:
    goal: str
    source: Path
    table: str
    required: tuple[str, ...]
    unique_by: tuple[str, ...]


def _names(value: object, maximum: int) -> tuple[str, ...]:
    if type(value) is not list or not 1 <= len(value) <= maximum:
        raise ValueError("SQLite rule needs a bounded nonempty column list")
    if any(type(x) is not str or not IDENT.fullmatch(x) for x in value):
        raise ValueError("invalid SQLite column identifier")
    if len({x.casefold() for x in value}) != len(value):
        raise ValueError("duplicate SQLite rule column")
    return tuple(value)


def validate_sqlite_goal(data: object, goal_file: Path) -> SqliteTableGoal:
    expected = {"version", "kind", "goal", "source", "table", "required", "unique_by"}
    if type(data) is not dict or set(data) != expected or (
        type(data["version"]) is not int or data["version"] != 1 or
        data["kind"] != "sqlite_table_audit"
    ):
        raise ValueError("invalid versioned sqlite_table_audit contract")
    title = data["goal"]
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(
        ord(char) < 32 for char in title
    ):
        raise ValueError("invalid SQLite audit goal title")
    path = data["source"]
    if type(path) is not str or not 1 <= len(path) <= 512 or any(
        char in "\\:" or ord(char) < 32 for char in path
    ):
        raise ValueError("SQLite source must be a local relative path")
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("SQLite source must stay inside goal directory")
    root = goal_file.parent.resolve(strict=True)
    source = (root / relative).resolve(strict=True)
    if not source.is_relative_to(root):
        raise ValueError("SQLite source symlink escapes goal directory")
    table = data["table"]
    if type(table) is not str or not IDENT.fullmatch(table) or table.lower().startswith("sqlite_"):
        raise ValueError("invalid or internal SQLite table name")
    required = _names(data["required"], 8)
    unique_by = _names(data["unique_by"], 3)
    if not set(unique_by) <= set(required):
        raise ValueError("unique key columns must also be required")
    return SqliteTableGoal(title.strip(), source, table, required, unique_by)


def source_digest(source: Path) -> str:
    if not source.is_file() or source.stat().st_size > MAX_DB_BYTES:
        raise ValueError("SQLite source must be a regular file <=16MiB")
    if any(source.with_name(source.name + suffix).exists()
           for suffix in ("-wal", "-journal")):
        raise ValueError("active SQLite WAL/journal is not a supported immutable snapshot")
    with source.open("rb") as stream:
        data = stream.read(MAX_DB_BYTES + 1)
    if len(data) > MAX_DB_BYTES or not data.startswith(b"SQLite format 3\x00"):
        raise ValueError("invalid, unbounded or unsupported SQLite source")
    return hashlib.sha256(data).hexdigest()


def is_blank(value: object) -> bool:
    return value is None or (
        type(value) in (str, bytes) and not value.strip()
    )


def _connect_and_read(goal: SqliteTableGoal) -> tuple[list[str], list[tuple]]:
    """No SQL from the goal; immutable URI and connection authorizer fail closed."""
    con = None
    try:
        con = sqlite3.connect(goal.source.as_uri() + "?mode=ro&immutable=1",
                              uri=True, timeout=0)
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA trusted_schema=OFF")
        schema = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (goal.table,)
        ).fetchone()
        if schema is None or type(schema[0]) is not str or not re.match(
            r"^CREATE\s+TABLE\b", schema[0], re.IGNORECASE
        ):
            raise ValueError("requested SQLite source is not an ordinary table")
        definitions = con.execute(
            'PRAGMA table_xinfo("' + goal.table + '")'
        ).fetchall()
        if not 1 <= len(definitions) <= MAX_COLS or any(
            item[6] != 0 or type(item[1]) is not str or
            not IDENT.fullmatch(item[1]) for item in definitions
        ):
            raise ValueError("SQLite table has unsupported columns")
        columns = [item[1] for item in definitions]
        if len({x.casefold() for x in columns}) != len(columns):
            raise ValueError("ambiguous SQLite column names")
        if not (set(goal.required) | set(goal.unique_by)) <= set(columns):
            raise ValueError("SQLite audit rule references unknown column")

        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and database == "main" and table == goal.table:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        con.set_authorizer(authorize)
        started = time.monotonic()
        con.set_progress_handler(
            lambda: int(time.monotonic() - started > 10), 1000
        )
        order = ", ".join('"' + column + '"' for column in columns)
        cursor = con.execute(
            'SELECT * FROM "' + goal.table + '" ORDER BY ' + order + ' LIMIT ?',
            (MAX_ROWS + 1,)
        )
        if [part[0] for part in cursor.description] != columns:
            raise ValueError("SQLite schema changed while opening table")
        rows = cursor.fetchall()
        if len(rows) > MAX_ROWS:
            raise ValueError("SQLite audit limit 20000 records exceeded")
        return columns, rows
    except sqlite3.Error as exc:
        raise ValueError("SQLite read-only table audit failed") from exc
    finally:
        if con is not None:
            con.close()


def execute_sqlite_goal(goal: SqliteTableGoal) -> dict:
    if type(goal) is not SqliteTableGoal:
        raise ValueError("SQLite goal was not validated")
    before = source_digest(goal.source)
    columns, rows = _connect_and_read(goal)
    pos = {name: i for i, name in enumerate(columns)}
    counts = {code: 0 for code in CODES}
    seen, affected, samples = set(), set(), []

    def record(index, code, column):
        counts[code] += 1
        affected.add(index)
        if len(samples) < MAX_SAMPLES:
            samples.append({"record": index, "code": code, "column": column})

    for index, row in enumerate(rows, start=1):
        for column in goal.required:
            if is_blank(row[pos[column]]):
                record(index, "MISSING_REQUIRED", column)
        key = tuple(row[pos[column]] for column in goal.unique_by)
        if not any(is_blank(item) for item in key):
            if key in seen:
                record(index, "DUPLICATE_KEY", ",".join(goal.unique_by))
            else:
                seen.add(key)
    if source_digest(goal.source) != before:
        raise ValueError("SQLite file changed during scan")
    status = "UNAVAILABLE" if not rows else (
        "CONFLICT" if any(counts.values()) else "AGREE"
    )
    return {
        "version": VERSION, "kind": "sqlite_table_audit", "goal": goal.goal,
        "filename": goal.source.name, "sha256": before,
        "table": goal.table, "columns": columns,
        "required": list(goal.required), "unique_by": list(goal.unique_by),
        "status": status, "rows": len(rows), "counts": counts,
        "affected_records": len(affected), "samples": samples, "scope": SCOPE
    }


def render_sqlite(report: dict) -> str:
    lines = [
        "EAI SQLite 원본 검사: " + report["status"],
        "DB: " + report["filename"] + " / SHA256 " + report["sha256"],
        "테이블: " + report["table"] + " / 레코드 " + str(report["rows"]),
        "누락 " + str(report["counts"]["MISSING_REQUIRED"]) +
        " / 중복 키 " + str(report["counts"]["DUPLICATE_KEY"])
    ]
    for sample in report["samples"]:
        lines.append(
            "레코드 " + str(sample["record"]) + ": " +
            sample["code"] + " / " + sample["column"]
        )
    return "\n".join(lines + [report["scope"]])
