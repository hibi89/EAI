"""P16 bounded local CSV quality gate. Values never leave the owner-selected file."""
from dataclasses import dataclass
from decimal import Decimal
import csv
import hashlib
import io
from pathlib import Path

from .analysis import _NUMBER, _render_decimal
from .decision_engine import _num
from .csv_analysis import MAX_FILE_BYTES, MAX_ROWS, MAX_COLUMNS, MAX_FIELD_CHARS, ALLOWED_ENCODINGS

VERSION = 'eai.goal.csv_quality.v1'
MAX_RULES = 8
MAX_SAMPLES = 10
CODES = ('MISSING_REQUIRED', 'DUPLICATE_KEY', 'NOT_NUMERIC', 'BELOW_MIN', 'ABOVE_MAX')
SCOPE = ('지정한 로컬 CSV의 누락·중복 키·숫자/범위 위반만 검사했습니다. '
         '행의 실제 값과 고유 키는 출력하지 않습니다. '
         '데이터 내용의 실세계 진실성·적정 임계값은 검증하지 않습니다. '
         '원본 수정, 자동 복구 및 외부 전송을 수행하지 않습니다.')


@dataclass(frozen=True)
class NumberRule:
    column: str
    minimum: Decimal
    maximum: Decimal


@dataclass(frozen=True)
class QualityGoal:
    goal: str
    source: Path
    encoding: str
    required: tuple[str, ...]
    unique_by: tuple[str, ...]
    numeric_rules: tuple[NumberRule, ...]


def _validate_names(raw: object, maximum: int, name: str) -> tuple[str, ...]:
    if type(raw) is not list or not 1 <= len(raw) <= maximum:
        raise ValueError(f'{name} requires 1-{maximum} column names')
    names = []
    for value in raw:
        if type(value) is not str or not 1 <= len(value.strip()) <= 60 or (
            value != value.strip() or any(ord(char) < 32 for char in value)
        ):
            raise ValueError('invalid CSV quality column name')
        names.append(value)
    if len({value.casefold() for value in names}) != len(names):
        raise ValueError('duplicate CSV quality column names')
    return tuple(names)


def validate_quality_goal(data: object, goal_file: Path) -> QualityGoal:
    expected = {'version','kind','goal','source','encoding','required',
                'unique_by','numeric_rules'}
    if type(data) is not dict or set(data) != expected or (
        type(data['version']) is not int or data['version'] != 1 or
        data['kind'] != 'csv_quality'
    ):
        raise ValueError('invalid versioned csv_quality contract')
    title = data['goal']
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(
        ord(char) < 32 for char in title
    ):
        raise ValueError('invalid CSV quality goal')
    raw_path = data['source']
    if type(raw_path) is not str or not 1 <= len(raw_path) <= 512 or any(
        char in '\\:' or ord(char) < 32 for char in raw_path
    ):
        raise ValueError('CSV source must be a local relative path')
    relative = Path(raw_path)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('CSV source must stay inside the goal directory')
    base = goal_file.parent.resolve(strict=True)
    source = (base / relative).resolve(strict=True)
    if not source.is_relative_to(base):
        raise ValueError('CSV source symlink escapes the goal directory')
    encoding = data['encoding']
    if type(encoding) is not str or encoding not in ALLOWED_ENCODINGS:
        raise ValueError('unsupported CSV quality encoding')
    required = _validate_names(data['required'],MAX_RULES,'required')
    unique_by = _validate_names(data['unique_by'],3,'unique_by')
    if not set(unique_by) <= set(required):
        raise ValueError('unique key columns must also be required')
    rules = data['numeric_rules']
    if type(rules) is not list or not 1 <= len(rules) <= MAX_RULES:
        raise ValueError('numeric_rules requires 1-8 exact ranges')
    numeric = []
    for item in rules:
        if type(item) is not dict or set(item) != {'column','min','max'}:
            raise ValueError('numeric rule must have column, min, max only')
        column = _validate_names([item['column']],1,'numeric rule')[0]
        minimum,maximum = _num(item['min'],'numeric.min'),_num(item['max'],'numeric.max')
        if minimum > maximum:
            raise ValueError('numeric minimum exceeds maximum')
        numeric.append(NumberRule(column,minimum,maximum))
    if len({x.column.casefold() for x in numeric}) != len(numeric):
        raise ValueError('duplicate numeric rule')
    return QualityGoal(title.strip(),source,encoding,required,unique_by,tuple(numeric))


def source_snapshot(path: Path) -> tuple[bytes,str]:
    """Open a bounded file once, fail closed on large or changing raw bytes."""
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('CSV quality source must be a regular file <=5MiB')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE_BYTES+1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('CSV quality source exceeds 5MiB')
    return raw,hashlib.sha256(raw).hexdigest()


def quality_contract(goal: QualityGoal) -> dict:
    return {'required':list(goal.required),'unique_by':list(goal.unique_by),
            'numeric_rules':[{'column':rule.column,'min':_render_decimal(rule.minimum),
                              'max':_render_decimal(rule.maximum)} for rule in goal.numeric_rules]}


def execute_quality_goal(goal: QualityGoal) -> dict:
    """Row-based single bounded scan, with counts and record indices only."""
    if type(goal) is not QualityGoal:
        raise ValueError('quality goal is not validated')
    binary,digest = source_snapshot(goal.source)
    counts = {code:0 for code in CODES}
    sample,affected,seen = [],set(),set()
    previous = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader = csv.reader(io.StringIO(binary.decode(goal.encoding),newline=''),strict=True)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise ValueError('CSV quality file is missing headers') from exc
        if not 1 <= len(headers) <= MAX_COLUMNS or any(
            not 1 <= len(x.strip()) <= 60 or x != x.strip() or
            any(ord(c) < 32 for c in x) for x in headers
        ) or len({x.casefold() for x in headers}) != len(headers):
            raise ValueError('invalid CSV quality headers')
        columns = {name:i for i,name in enumerate(headers)}
        needed = set(goal.required)|set(goal.unique_by)|{x.column for x in goal.numeric_rules}
        if not needed <= set(columns):
            raise ValueError('CSV quality rule references an unknown column')

        def violation(record: int,code: str,column: str) -> None:
            counts[code] += 1
            affected.add(record)
            if len(sample) < MAX_SAMPLES:
                sample.append({'record':record,'code':code,'column':column})

        records = 0
        for row in reader:
            records += 1
            if records > MAX_ROWS:
                raise ValueError('CSV quality limit 20000 records exceeded')
            if len(row) != len(headers) or any(len(cell)>MAX_FIELD_CHARS for cell in row):
                raise ValueError('CSV quality row/field length mismatch')
            for col in goal.required:
                if not row[columns[col]].strip():
                    violation(records,'MISSING_REQUIRED',col)
            key = tuple(row[columns[col]].strip() for col in goal.unique_by)
            if all(key):
                if key in seen:
                    violation(records,'DUPLICATE_KEY',','.join(goal.unique_by))
                else:
                    seen.add(key)
            for rule in goal.numeric_rules:
                value = row[columns[rule.column]].strip()
                if not value:
                    continue  # optional missing numeric is not treated as zero
                if not _NUMBER.fullmatch(value):
                    violation(records,'NOT_NUMERIC',rule.column)
                else:
                    number = Decimal(value)
                    if number < rule.minimum:
                        violation(records,'BELOW_MIN',rule.column)
                    elif number > rule.maximum:
                        violation(records,'ABOVE_MAX',rule.column)
    finally:
        csv.field_size_limit(previous)
    if source_snapshot(goal.source)[1] != digest:
        raise ValueError('CSV quality source changed during scan')
    status = 'UNAVAILABLE' if records == 0 else (
        'CONFLICT' if any(counts.values()) else 'AGREE')
    return {'version':VERSION,'kind':'csv_quality','goal':goal.goal,
            'filename':goal.source.name,'sha256':digest,'encoding':goal.encoding,
            'status':status,'rows':records,'columns':headers,
            'rules':quality_contract(goal),'counts':counts,
            'affected_records':len(affected),'samples':sample,'scope':SCOPE}


def render_quality(report: dict) -> str:
    lines=[f"EAI CSV 데이터 품질: {report['status']}",
           f"파일: {report['filename']} / SHA256 {report['sha256']}",
           f"레코드: {report['rows']}, 문제 레코드: {report['affected_records']}",
           "위반 유형: "+', '.join(f"{k}={v}" for k,v in report['counts'].items())]
    for item in report['samples']:
        lines.append(f"레코드 {item['record']}: {item['code']} / {item['column']}")
    lines.append(report['scope'])
    return '\n'.join(lines)
