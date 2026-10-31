"""Bounded CPU reconciliation of two explicitly selected local CSV datasets.

Compares keyed numeric observations rather than merely aggregate totals.
AGREE means a scoped data-to-data match, NOT a statement of external truth.
No model, network, persistence or modification of source files.
"""
import csv
from decimal import Decimal, localcontext
from pathlib import Path

from .analysis import _NUMBER, _render_decimal
from .csv_analysis import (ALLOWED_ENCODINGS, MAX_FIELD_CHARS,
                           MAX_ROWS, inspect_csv)
from .verify_csv import _file_digest, _numeric

MAX_KEY_CHARS = 120
MAX_DETAILS = 20


def _parse_rows(path: Path, key: str, value: str, encoding: str) -> tuple[dict, dict[str, str | None]]:
    """Validate shape using the existing P2 bounded parser, then index only two fields."""
    before = _file_digest(path)
    profile = inspect_csv(path, encoding=encoding)
    names = [s['name'] for s in profile['stats']]
    if key not in names or value not in names:
        if before != _file_digest(path):
            raise ValueError(f'{path.name}: 열을 확인하는 중 원본 CSV가 변경됐습니다.')
        return ({'filename': path.name, 'sha256': before, 'rows': profile['rows'],
                 'columns': profile['columns'], 'missing_columns': [x for x in (key, value) if x not in names]}, {})

    key_pos, value_pos = names.index(key), names.index(value)
    index: dict[str, str | None] = {}
    old_field_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        with path.open('r', encoding=encoding, newline='') as f:
            reader = csv.reader(f, strict=True)
            header = next(reader)
            if header != names:
                raise ValueError(f'{path.name}: CSV 헤더가 스캔 도중 변경됐습니다.')
            count = 0
            for row in reader:
                count += 1
                if count > MAX_ROWS or len(row) != len(names):
                    raise ValueError(f'{path.name}: 행 수·열 수 제한을 초과했습니다.')
                item_key = row[key_pos]
                if (not 1 <= len(item_key) <= MAX_KEY_CHARS or
                        item_key.strip() != item_key or any(ord(c) < 32 for c in item_key)):
                    raise ValueError(f'{path.name}: 빈 키, 긴 키 또는 제어문자가 존재합니다.')
                if item_key in index:
                    raise ValueError(f'{path.name}: 고유 키가 중복되어 비교할 수 없습니다.')
                # Invalid/non-numeric observations are UNAVAILABLE, not silently zero.
                number = row[value_pos].strip()
                index[item_key] = number if _NUMBER.fullmatch(number) else None
            if count != profile['rows']:
                raise ValueError(f'{path.name}: 데이터 행 수가 스캔 도중 변경됐습니다.')
    finally:
        csv.field_size_limit(old_field_limit)
    after = _file_digest(path)
    if before != after:
        raise ValueError(f'{path.name}: 검증 도중 원본 CSV가 변경됐습니다.')
    return ({'filename': path.name, 'sha256': before, 'rows': profile['rows'],
             'columns': profile['columns'], 'missing_columns': []}, index)


def reconcile_csv(left: str | Path, right: str | Path, *, key: str, value: str,
                  tolerance: str = '0', encoding: str = 'utf-8-sig') -> dict:
    """Read-only keyed reconciliation with bounded report and exact decimal math.

    Status order: contradictory values or absent keys -> CONFLICT;
    then unavailable numeric values/schema/duplicate file bytes -> UNAVAILABLE;
    otherwise AGREE. All results are scoped to *these two files only*.
    """
    if encoding not in ALLOWED_ENCODINGS:
        raise ValueError('허용되지 않은 CSV 인코딩')
    if (type(key) is not str or type(value) is not str or
            not 1 <= len(key) <= 60 or not 1 <= len(value) <= 60 or
            key.strip() != key or value.strip() != value or key == value or
            any(ord(c) < 32 for c in key + value)):
        raise ValueError('고유 키 열과 비교할 숫자 열을 서로 다르게 지정하세요.')
    tol = _numeric(tolerance, 'tolerance')
    if tol < 0:
        raise ValueError('허용 오차는 음수일 수 없습니다.')
    p1, p2 = (Path(p).expanduser().resolve(strict=True) for p in (left, right))
    if p1 == p2:
        raise ValueError('동일한 CSV 파일을 두 번 지정할 수 없습니다.')
    source_a, a = _parse_rows(p1, key, value, encoding)
    source_b, b = _parse_rows(p2, key, value, encoding)

    missing_columns = bool(source_a['missing_columns'] or source_b['missing_columns'])
    duplicate_bytes = source_a['sha256'] == source_b['sha256']
    if missing_columns:
        return dict(status='UNAVAILABLE', sources=[source_a, source_b],
                    columns={'key': key, 'value': value}, tolerance=_render_decimal(tol),
                    counts={'agree': 0, 'different': 0, 'left_only': 0, 'right_only': 0,
                            'non_numeric': 0}, differences=[], truncated=0,
                    warnings=['해당 열이 없는 파일이 있습니다. 동일한 열 이름이 필요합니다.'],
                    scope='두 CSV 파일의 값만 비교했습니다. 원본의 진위·단위·시점을 검증하지 않았습니다.')

    counts = {'agree': 0, 'different': 0, 'left_only': 0, 'right_only': 0,
              'non_numeric': 0}
    details = []
    total_detail = 0

    def capture(kind: str, identifier: str, old: str | None, new: str | None,
                delta: str | None = None) -> None:
        nonlocal total_detail
        total_detail += 1
        if len(details) < MAX_DETAILS:
            details.append({'kind': kind, 'key': identifier, 'left': old,
                            'right': new, 'absolute_delta': delta})

    with localcontext() as ctx:
        ctx.prec = 90
        for identifier in sorted(a.keys() | b.keys()):
            old, new = a.get(identifier), b.get(identifier)
            if identifier not in a:
                counts['right_only'] += 1
                capture('RIGHT_ONLY', identifier, None, new)
            elif identifier not in b:
                counts['left_only'] += 1
                capture('LEFT_ONLY', identifier, old, None)
            elif old is None or new is None:
                counts['non_numeric'] += 1
                capture('NON_NUMERIC', identifier, old, new)
            else:
                delta = abs(Decimal(old) - Decimal(new))
                if delta <= tol:
                    counts['agree'] += 1
                else:
                    counts['different'] += 1
                    capture('DIFFERENT', identifier, old, new, _render_decimal(delta))

    if counts['different'] or counts['left_only'] or counts['right_only']:
        status = 'CONFLICT'
    elif counts['non_numeric'] or duplicate_bytes:
        status = 'UNAVAILABLE'
    else:
        status = 'AGREE'
    warnings = []
    if duplicate_bytes:
        warnings.append('파일 내용 해시가 동일합니다. 별개의 독립 증거로 간주할 수 없습니다.')
    if counts['non_numeric']:
        warnings.append('일부 비교 값이 비어 있거나 유효한 십진수가 아닙니다.')
    if source_a['rows'] != source_b['rows']:
        warnings.append('CSV 행 수가 다릅니다. 키 누락 내역을 확인하세요.')
    return {
        'status': status, 'sources': [source_a, source_b],
        'columns': {'key': key, 'value': value}, 'tolerance': _render_decimal(tol),
        'counts': counts, 'differences': details, 'truncated': total_detail - len(details),
        'warnings': warnings,
        'scope': ('두 CSV 파일의 명시된 키별 수치만 비교했습니다. 값이 같더라도 '
                  '데이터 원본의 진위·독립성·단위·시점·실세계 사실은 증명하지 않았습니다.'),
    }


def render_reconciliation(report: dict) -> str:
    first, second = report['sources']
    lines = [f"EAI 교차검증: {report['status']}",
             f"A: {first['filename']} / SHA256 {first['sha256']}",
             f"B: {second['filename']} / SHA256 {second['sha256']}",
             f"키={report['columns']['key']}, 값={report['columns']['value']}, 허용오차={report['tolerance']}"]
    lines.extend(f'{name}: {number}' for name, number in report['counts'].items())
    for entry in report['differences']:
        lines.append(f"{entry['kind']} key={entry['key']}: A={entry['left']}, B={entry['right']}"
                     + (f", 절대 차이={entry['absolute_delta']}" if entry['absolute_delta'] is not None else ''))
    if report['truncated']:
        lines.append(f"상세 차이 {report['truncated']}건은 표시 제한으로 생략했습니다.")
    lines.extend(report['warnings'])
    lines.append(report['scope'])
    return '\n'.join(lines)
