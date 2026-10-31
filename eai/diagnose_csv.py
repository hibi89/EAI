"""CPU-only, bounded multi-metric source discrepancy diagnostics.

This composes the verified P4 keyed comparator; it finds *where* two sources
conflict and suggests inspection priorities. It cannot determine *which source*
is true or prove the physical cause of a mismatch.
"""
from collections import defaultdict
from pathlib import Path

from .analysis import _render_decimal
from .csv_analysis import ALLOWED_ENCODINGS
from .reconcile_csv import reconcile_csv
from .verify_csv import _file_digest, _numeric

MAX_METRICS = 8
MAX_CANDIDATES = 20
MAX_SIGNALS_PER_CANDIDATE = 8


def _validate(key: str, values: list[str], tolerance: str, encoding: str) -> str:
    if encoding not in ALLOWED_ENCODINGS:
        raise ValueError('지원하지 않는 CSV 인코딩입니다.')
    if not isinstance(key, str) or not 1 <= len(key) <= 60 or key.strip() != key or any(ord(c) < 32 for c in key):
        raise ValueError('키 열 이름은 1~60자이며 공백·제어문자를 포함할 수 없습니다.')
    if type(values) is not list or not 1 <= len(values) <= MAX_METRICS:
        raise ValueError(f'비교 지표는 1~{MAX_METRICS}개가 필요합니다.')
    seen = set()
    for value in values:
        if (type(value) is not str or not 1 <= len(value) <= 60 or value.strip() != value
                or any(ord(c) < 32 for c in value) or value == key or value in seen):
            raise ValueError('각 수치 열은 고유해야 하며 키 열과 서로 달라야 합니다.')
        seen.add(value)
    t = _numeric(tolerance, 'tolerance')
    if t < 0:
        raise ValueError('허용 오차는 음수일 수 없습니다.')
    return _render_decimal(t)


def _hypothesis(kinds: set[str], metric_count: int) -> tuple[str, str]:
    """Explanations are candidates only: no causal certainty or source blame."""
    if 'LEFT_ONLY' in kinds or 'RIGHT_ONLY' in kinds:
        return ('KEY_COVERAGE_DIFFERENCE', '파일 간 키 포함 범위·추출 조건 또는 누락 기록을 점검할 후보입니다.')
    if 'NON_NUMERIC' in kinds:
        return ('VALUE_TYPE_ISSUE', '빈 값·문자 값·자료 형식이 달라졌는지 확인할 후보입니다.')
    if metric_count >= 2:
        return ('MULTI_METRIC_DRIFT', '같은 키의 여러 지표가 달라 자료 버전·수정·연결 기준을 확인할 후보입니다.')
    return ('SINGLE_METRIC_DIFFERENCE', '해당 키의 수치 변경·집계 기준 차이를 확인할 후보입니다.')


def diagnose_csv(left: str | Path, right: str | Path, *, key: str,
                 values: list[str], tolerance: str = '0', encoding: str = 'utf-8-sig') -> dict:
    """Compare up to eight numeric fields across two user-selected CSVs.

    Re-uses P4 validation and data-drift detection. Full discrepancy counts are
    exact *per metric*; candidate keys are bounded samples of P4 details, and
    must never be described as complete when P4 reports truncation.
    """
    tol = _validate(key, values, tolerance, encoding)
    left_path = Path(left).expanduser().resolve(strict=True)
    right_path = Path(right).expanduser().resolve(strict=True)
    if left_path == right_path:
        raise ValueError('서로 다른 두 CSV 파일을 명시해야 합니다.')

    # Anchor each file before any metric-level verification.
    left_digest, right_digest = _file_digest(left_path), _file_digest(right_path)
    metric_reports = []
    observations: dict[str, list[dict]] = defaultdict(list)
    for value in values:
        report = reconcile_csv(left_path, right_path, key=key, value=value,
                               tolerance=tol, encoding=encoding)
        sources = report['sources']
        if (sources[0]['sha256'] != left_digest or sources[1]['sha256'] != right_digest):
            raise ValueError('지표 비교 사이에 원본 CSV가 변경되어 진단을 중단했습니다.')
        metric_reports.append({
            'metric': value,
            'status': report['status'],
            'counts': report['counts'],
            'truncated': report['truncated'],
            'warnings': report['warnings'],
            'missing_columns': [s['missing_columns'] for s in sources],
        })
        for item in report['differences']:
            observations[item['key']].append({
                'metric': value, 'kind': item['kind'], 'left': item['left'],
                'right': item['right'], 'absolute_delta': item['absolute_delta'],
            })

    # Detect change even between independently verified metrics and final output.
    if left_digest != _file_digest(left_path) or right_digest != _file_digest(right_path):
        raise ValueError('진단 종료 전 원본 CSV 변경이 감지됐습니다.')

    candidates = []
    for identifier, signals in observations.items():
        metrics = sorted({s['metric'] for s in signals})
        categories = {s['kind'] for s in signals}
        label, explanation = _hypothesis(categories, len(metrics))
        # Priority sorts by independent signals/count, never by raw numeric delta:
        # mixed units can make a larger number less significant.
        priority = (len(metrics),
                    sum(s['kind'] == 'DIFFERENT' for s in signals),
                    int('LEFT_ONLY' in categories or 'RIGHT_ONLY' in categories))
        candidates.append((priority, identifier, {
            'key': identifier, 'affected_metrics': metrics,
            'hypothesis_code': label,
            'investigation_hint': explanation,
            'evidence': signals[:MAX_SIGNALS_PER_CANDIDATE],
        }))
    candidates.sort(key=lambda x: (-x[0][0], -x[0][1], -x[0][2], x[1]))
    selected = [item[2] for item in candidates[:MAX_CANDIDATES]]
    truncated_per_metric = {m['metric']: m['truncated'] for m in metric_reports if m['truncated']}
    statuses = [m['status'] for m in metric_reports]
    status = ('CONFLICT' if 'CONFLICT' in statuses
              else 'UNAVAILABLE' if 'UNAVAILABLE' in statuses else 'AGREE')
    if status == 'AGREE' and not any(m['counts']['agree'] for m in metric_reports):
        # Empty matched sets are not affirmative evidence of numeric agreement.
        status = 'UNAVAILABLE'
    return {
        'status': status,
        'sources': [{'filename': left_path.name, 'sha256': left_digest},
                    {'filename': right_path.name, 'sha256': right_digest}],
        'key_column': key, 'metrics': metric_reports, 'tolerance': tol,
        'candidates': selected, 'candidate_keys_displayed': len(selected),
        'candidate_keys_omitted': len(candidates) - len(selected),
        'truncated_per_metric': truncated_per_metric,
        'sampling_limitations': (
            '원래 P4 지표별 차이 상세는 선두 20건만 제공하므로, 이 목록은 전체 충돌 키의 순위가 '
            '아닐 수 있습니다. 각 지표의 전체 건수는 counts에 포함됩니다.'
            if truncated_per_metric else '모든 감지된 충돌 키에 대해 상세 후보를 만들었습니다.'),
        'scope': ('두 CSV 내부의 키별 불일치 신호만 진단했습니다. 원본 중 어느 쪽이 맞는지, '
                  '실제 원인·단위·기간·자료 진위·출처의 독립성은 확인하지 않았습니다.'),
    }


def render_diagnosis(report: dict) -> str:
    lines = [f"EAI P5 다중 지표 원인 후보: {report['status']}",
             'A: ' + report['sources'][0]['filename'] + ' / SHA256 ' + report['sources'][0]['sha256'],
             'B: ' + report['sources'][1]['filename'] + ' / SHA256 ' + report['sources'][1]['sha256'],
             f"키: {report['key_column']}, 공통 절대 허용 오차: {report['tolerance']}"]
    for m in report['metrics']:
        counts = ', '.join(f'{k}={v}' for k, v in m['counts'].items())
        lines.append(f"{m['metric']}: {m['status']} ({counts}; 생략 상세={m['truncated']})")
    for c in report['candidates']:
        lines.append(f"후보 key={c['key']} / {c['hypothesis_code']} / "
                     f"지표={','.join(c['affected_metrics'])}")
        for s in c['evidence']:
            lines.append(f"  {s['metric']} {s['kind']}: A={s['left']} B={s['right']} "
                         f"delta={s['absolute_delta']}")
        lines.append('  확인할 가능성: ' + c['investigation_hint'])
    if report['candidate_keys_omitted']:
        lines.append(f"키 후보 {report['candidate_keys_omitted']}개는 출력 제한으로 생략했습니다.")
    lines.extend([report['sampling_limitations'], report['scope']])
    return '\n'.join(lines)
