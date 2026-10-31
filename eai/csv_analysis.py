"""Owner-invoked, read-only local CSV profile; no LLM, GPU or network.

A narrow streaming scan: no row content is persisted or sent to remote services.
"""
import csv
from decimal import Decimal, localcontext
from pathlib import Path

from .analysis import _NUMBER, _render_decimal

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000
MAX_COLUMNS = 32
MAX_FIELD_CHARS = 4096
ALLOWED_ENCODINGS = frozenset({'utf-8-sig', 'utf-8', 'cp949'})


def inspect_csv(path: str | Path, *, encoding: str = 'utf-8-sig') -> dict:
    """Summarize user-selected CSV by numeric column, with explicit resource bounds."""
    if encoding not in ALLOWED_ENCODINGS:
        raise ValueError('허용된 인코딩: utf-8-sig, utf-8, cp949')
    filename = Path(path).expanduser().resolve(strict=True)
    if not filename.is_file():
        raise ValueError('CSV 일반 파일만 분석할 수 있습니다.')
    if filename.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('CSV 최대 크기 5MiB 초과')

    # Prevent a giant CSV field from exhausting memory in the standard parser.
    previous_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        with filename.open('r', encoding=encoding, newline='') as stream:
            reader = csv.reader(stream, strict=True)
            try:
                headers = next(reader)
            except StopIteration as exc:
                raise ValueError('헤더가 없는 CSV 파일입니다.') from exc
            if not 1 <= len(headers) <= MAX_COLUMNS:
                raise ValueError('CSV 열 수는 1~32개여야 합니다.')
            if any(not 1 <= len(head.strip()) <= 60 or any(ord(c) < 32 for c in head)
                   for head in headers) or len({h.strip().casefold() for h in headers}) != len(headers):
                raise ValueError('빈 열 이름, 중복 열 이름 또는 제어문자는 허용되지 않습니다.')
            stats = [dict(name=head, empty=0, numeric=0, text=0, min=None, max=None, sum=Decimal(0))
                     for head in headers]
            rows = 0
            with localcontext() as ctx:
                ctx.prec = 90
                for row in reader:
                    rows += 1
                    if rows > MAX_ROWS:
                        raise ValueError('CSV 최대 행 수 20,000개 초과')
                    if len(row) != len(headers):
                        raise ValueError(f'{rows + 1}행: 헤더와 열 수가 일치하지 않습니다.')
                    for value, state in zip(row, stats):
                        if len(value) > MAX_FIELD_CHARS:
                            raise ValueError('CSV 셀 최대 길이 4,096자 초과')
                        value = value.strip()
                        if not value:
                            state['empty'] += 1
                        elif _NUMBER.fullmatch(value):
                            # Decimal is exact for bounded fixed-point input.
                            number = Decimal(value)
                            state['numeric'] += 1
                            state['sum'] += number
                            state['min'] = number if state['min'] is None else min(state['min'], number)
                            state['max'] = number if state['max'] is None else max(state['max'], number)
                        else:
                            state['text'] += 1
                summary = []
                for state in stats:
                    count = state['numeric']
                    is_numeric = count > 0 and state['text'] == 0
                    summary.append({
                        'name': state['name'],
                        'missing': state['empty'],
                        'type': 'numeric' if is_numeric else ('mixed' if count else 'text'),
                        'numeric_count': count,
                        'text_count': state['text'],
                        'sum': _render_decimal(state['sum']) if is_numeric else None,
                        'min': _render_decimal(state['min']) if is_numeric else None,
                        'max': _render_decimal(state['max']) if is_numeric else None,
                        'avg': _render_decimal((state['sum'] / count).quantize(Decimal('0.000001')))
                               if is_numeric else None,
                    })
        return {'rows': rows, 'columns': len(headers), 'stats': summary,
                'notes': ['사용자가 지정한 로컬 CSV만 분석했습니다.',
                          '단위·날짜·원본 사실관계는 검증하지 않았습니다.',
                          '숫자 평균은 소수점 여섯 자리로 반올림했습니다.']}
    finally:
        csv.field_size_limit(previous_limit)


def render_csv_summary(report: dict) -> str:
    lines = [f"EAI 로컬 CSV 요약 — {report['rows']}행, {report['columns']}열"]
    for state in report['stats']:
        desc = f"{state['name']}: {state['type']}, 누락 {state['missing']}"
        if state['type'] == 'numeric':
            desc += (f", 유효숫자 {state['numeric_count']}, 합계 {state['sum']}, "
                     f"최소 {state['min']}, 최대 {state['max']}, 평균 {state['avg']}")
        lines.append(desc)
    return '\n'.join(lines + report['notes'])
