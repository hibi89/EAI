"""Read-only, bounded verification of numerical claims against one local CSV.

VERIFIED means equality within declared tolerance *relative to the supplied file*,
not external factual truth or provenance authenticity. No LLM, GPU, or network.
"""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .analysis import _NUMBER
from .csv_analysis import inspect_csv, MAX_FILE_BYTES

METRICS = frozenset({'sum', 'min', 'max', 'avg', 'missing', 'numeric_count', 'text_count'})
MAX_CLAIMS = 24
MAX_CLAIMS_BYTES = 32 * 1024
READ_BYTES = 64 * 1024


def _numeric(raw: object, what: str) -> Decimal:
    if type(raw) is not str or not _NUMBER.fullmatch(raw):
        raise ValueError(f'{what}: 숫자는 제한된 십진수 문자열이어야 합니다.')
    return Decimal(raw)


def validate_claims(raw: object) -> list[dict]:
    """Pure JSON-compatible typed claim validation, no field-name interpretation."""
    if type(raw) is not list or not 1 <= len(raw) <= MAX_CLAIMS:
        raise ValueError(f'검증 주장은 1~{MAX_CLAIMS}개여야 합니다.')
    result = []
    for index, claim in enumerate(raw, start=1):
        if type(claim) is not dict or not {'column', 'metric', 'expected'} <= set(claim) or (
                set(claim) - {'column', 'metric', 'expected', 'tolerance'}):
            raise ValueError(f'{index}번 주장: column/metric/expected/tolerance 필드를 확인하세요.')
        column, metric = claim['column'], claim['metric']
        if type(column) is not str or not 1 <= len(column) <= 60 or column != column.strip():
            raise ValueError(f'{index}번 주장: 열 이름이 잘못됐습니다.')
        if type(metric) is not str or metric not in METRICS:
            raise ValueError(f'{index}번 주장: 지원되지 않는 지표입니다.')
        expected = _numeric(claim['expected'], 'expected')
        tolerance = _numeric(claim.get('tolerance', '0'), 'tolerance')
        if tolerance < 0:
            raise ValueError('허용 오차는 음수일 수 없습니다.')
        result.append(dict(column=column, metric=metric, expected=expected, tolerance=tolerance))
    return result


def load_claims(path: str | Path) -> list[dict]:
    filename = Path(path).expanduser().resolve(strict=True)
    if not filename.is_file() or filename.stat().st_size > MAX_CLAIMS_BYTES:
        raise ValueError('주장 파일은 32KiB 이하의 일반 JSON 파일이어야 합니다.')
    with filename.open('rb') as stream:
        payload = stream.read(MAX_CLAIMS_BYTES + 1)
    if len(payload) > MAX_CLAIMS_BYTES:
        raise ValueError('주장 JSON이 너무 큽니다.')

    def strict_object(items):
        parsed = {}
        for key, value in items:
            if key in parsed:
                raise ValueError('주장 JSON의 중복 키는 허용되지 않습니다.')
            parsed[key] = value
        return parsed

    try:
        raw = json.loads(payload.decode('utf-8-sig'), object_pairs_hook=strict_object)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('주장 JSON 파일을 해석할 수 없습니다.') from exc
    return validate_claims(raw)


def _file_digest(path: Path) -> str:
    if not path.is_file():
        raise ValueError('일반 CSV 파일만 분석할 수 있습니다.')
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('CSV 최대 크기 5MiB 초과')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(READ_BYTES):
            digest.update(chunk)
            if stream.tell() > MAX_FILE_BYTES:
                raise ValueError('CSV 최대 크기 5MiB 초과')
    return digest.hexdigest()


def verify_csv_claims(path: str | Path, claims: list[dict], *, encoding: str = 'utf-8-sig') -> dict:
    validated = validate_claims(claims)
    filename = Path(path).expanduser().resolve(strict=True)
    before = _file_digest(filename)
    profile = inspect_csv(filename, encoding=encoding)
    after = _file_digest(filename)
    if before != after:
        raise ValueError('검증 중 CSV 내용이 변경되어 결과를 무효화했습니다.')

    columns = {entry['name']: entry for entry in profile['stats']}
    verdicts = []
    for claim in validated:
        name, metric = claim['column'], claim['metric']
        evidence = columns.get(name)
        actual = None if evidence is None else evidence.get(metric)
        if (evidence is None or actual is None or
                (metric in {'sum', 'min', 'max', 'avg'} and evidence['type'] != 'numeric')):
            status = 'UNAVAILABLE'
            delta = None
        else:
            try:
                observed = Decimal(str(actual))
            except (ValueError, TypeError) as exc:
                raise ValueError('CSV 통계 결과의 수치 형식 오류') from exc
            delta_value = abs(observed - claim['expected'])
            delta = format(delta_value, 'f')
            status = 'VERIFIED' if delta_value <= claim['tolerance'] else 'CONFLICT'
        verdicts.append({
            'status': status, 'column': name, 'metric': metric,
            'expected': format(claim['expected'], 'f'),
            'actual': None if actual is None or status == 'UNAVAILABLE' else str(actual),
            'absolute_delta': delta,
            'tolerance': format(claim['tolerance'], 'f'),
        })

    overall = ('CONFLICT' if any(v['status'] == 'CONFLICT' for v in verdicts)
               else 'UNAVAILABLE' if any(v['status'] == 'UNAVAILABLE' for v in verdicts)
               else 'VERIFIED')
    return {
        'status': overall,
        'source': {'filename': filename.name, 'sha256': before,
                   'rows': profile['rows'], 'columns': profile['columns']},
        'claims': verdicts,
        'scope': ('주어진 CSV 파일의 수치와 주장만 대조했습니다. 파일 원본의 진위, '
                  '단위, 기간 또는 외부 사실은 검증하지 않았습니다.'),
        'precision': 'avg는 CSV 분석기의 소수점 6자리 반올림값 기준입니다.',
    }


def render_verification(report: dict) -> str:
    lines = [f"EAI CSV 주장 검증: {report['status']}",
             f"원본: {report['source']['filename']} / SHA256: {report['source']['sha256']}",
             f"데이터: {report['source']['rows']}행 / {report['source']['columns']}열"]
    for i, item in enumerate(report['claims'], start=1):
        actual = item['actual'] if item['actual'] is not None else '계산 불가'
        lines.append(f"{i}. {item['column']}.{item['metric']} = {item['expected']} 주장 → "
                     f"관측 {actual}: {item['status']} (허용 오차 {item['tolerance']})")
    lines.extend((report['scope'], report['precision']))
    return '\n'.join(lines)
