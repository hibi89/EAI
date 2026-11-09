"""Independent, CPU-only postcondition checks for typed EAI goal receipts.

These guards reject forged/contradictory solver metadata; they do not prove the
trustworthiness of user-provided inputs or amount to general AI reasoning.
"""
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from .decision_engine import ChoiceGoal
from .plan_engine import AuditGoal, PLAN_VERSION
from .verify_csv import _file_digest
from .receipt_evidence import verify_choice_display_evidence
from .task_portfolio import TaskGoal, verify_task_receipt
from .task_schedule import ScheduleGoal
from .schedule_receipt import verify_schedule_receipt
from .csv_quality import QualityGoal
from .quality_receipt import verify_quality_receipt
from .csv_schema_drift import DriftGoal
from .drift_receipt import verify_drift_receipt
from .sqlite_table_audit import SqliteTableGoal
from .sqlite_receipt import verify_sqlite_receipt
from .csv_relationships import RelationshipGoal
from .relationship_receipt import verify_relationship_receipt
from .local_evidence_search import EvidenceSearchGoal
from .evidence_search_receipt import verify_search_receipt

GUARD_VERSION = 'eai.receipt.guard.v1'
ALLOWED_STATUS = {
    'choose_options': frozenset({'DECIDED', 'TIE', 'UNAVAILABLE'}),
    'csv_audit': frozenset({'AGREE', 'CONFLICT', 'UNAVAILABLE'}),
    'plan_tasks': frozenset({'DECIDED', 'TIE', 'UNAVAILABLE'}),
    'schedule_tasks': frozenset({'DECIDED', 'UNAVAILABLE'}),
    'csv_quality': frozenset({'AGREE', 'CONFLICT', 'UNAVAILABLE'}),
    'csv_schema_drift': frozenset({'AGREE', 'CONFLICT', 'UNAVAILABLE'}),
    'sqlite_table_audit': frozenset({'AGREE', 'CONFLICT', 'UNAVAILABLE'}),
    'csv_relationships': frozenset({'AGREE', 'CONFLICT', 'UNAVAILABLE'}),
    'local_evidence_search': frozenset({'AGREE', 'UNAVAILABLE'}),
}
MAX_DIAGNOSTIC_OPTIONS = 12


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError('EAI 영수증 검증 실패: ' + message)


def _positive_or_zero_decimal(text: object) -> Decimal:
    _check(isinstance(text, str) and len(text) <= 64, '점수 형식이 잘못됐습니다')
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('EAI 영수증 검증 실패: 점수 형식이 잘못됐습니다') from exc
    _check(number.is_finite() and 0 <= number <= 100, '점수 범위를 벗어났습니다')
    return number


def _dominates(a, b, criteria):
    strictly_better = False
    for c in criteria:
        va, vb = a.values[c.id], b.values[c.id]
        if va is None or vb is None:
            return False
        if c.direction == 'min':
            if va > vb:
                return False
            strictly_better |= va < vb
        else:
            if va < vb:
                return False
            strictly_better |= va > vb
    return strictly_better


def _choice_diagnostics(goal: ChoiceGoal, entries: dict[str, dict], status: str) -> dict:
    if status == 'DECIDED':
        return {'type': 'NONE', 'action_required': False, 'items': []}
    if status == 'TIE':
        return {'type': 'TIE_REVIEW', 'action_required': True,
                'items': [{'code': 'USER_PREFERENCE_REQUIRED',
                           'hint': '동점 후보에 대해 우선순위나 추가 평가 기준을 지정하세요.'}]}
    issues = []
    for option in goal.options[:MAX_DIAGNOSTIC_OPTIONS]:
        row = entries[option.id]
        if row['missing']:
            issues.append({'option': option.id, 'code': 'MISSING_VALUES',
                           'fields': list(row['missing'])})
        elif row['constraint_breaches']:
            issues.append({'option': option.id, 'code': 'HARD_CONSTRAINT',
                           'fields': sorted({b['criterion'] for b in row['constraint_breaches']})})
    return {'type': 'NO_FEASIBLE_OPTION', 'action_required': True,
            'items': issues, 'items_omitted': max(0, len(goal.options) - MAX_DIAGNOSTIC_OPTIONS),
            'hint': '누락값이나 필수조건을 검토하세요. EAI가 기준을 임의로 완화하지 않습니다.'}


def _verify_choice(goal: ChoiceGoal, report: dict) -> tuple[list[str], dict]:
    _check(report.get('kind') == 'choose_options' and report.get('goal') == goal.goal,
           '다른 목표의 결과입니다')
    entries = report.get('options')
    _check(type(entries) is list and len(entries) == len(goal.options), '후보 개수가 맞지 않습니다')
    indexed = {}
    expected_ids = {o.id for o in goal.options}
    for entry in entries:
        _check(type(entry) is dict and type(entry.get('id')) is str, '후보 항목이 잘못됐습니다')
        _check(entry['id'] in expected_ids and entry['id'] not in indexed, '후보 ID가 잘못됐습니다')
        indexed[entry['id']] = entry
    _check(set(indexed) == expected_ids, '후보가 누락됐습니다')
    feasible = {}
    expected_scores = {}
    for option in goal.options:
        missing = sorted(c.id for c in goal.criteria if option.values[c.id] is None)
        violations = set()
        for c in goal.criteria:
            value = option.values[c.id]
            if value is None:
                continue
            if c.hard_min is not None and value < c.hard_min:
                violations.add((c.id, 'hard_min'))
            if c.hard_max is not None and value > c.hard_max:
                violations.add((c.id, 'hard_max'))
        expected = 'UNAVAILABLE' if missing else 'EXCLUDED' if violations else 'FEASIBLE'
        entry = indexed[option.id]
        _check(entry.get('status') == expected, f'{option.id} 제약 판정 불일치')
        _check(entry.get('missing') == missing, f'{option.id} 누락값 목록 불일치')
        breaches = entry.get('constraint_breaches')
        _check(type(breaches) is list, f'{option.id} 제약 목록 형식 오류')
        recorded = set()
        for b in breaches:
            _check(type(b) is dict and type(b.get('criterion')) is str
                   and b.get('rule') in {'hard_min', 'hard_max'}, '제약 기록이 잘못됐습니다')
            recorded.add((b['criterion'], b['rule']))
        _check(recorded == violations and len(recorded) == len(breaches), '제약 기록과 입력이 불일치')
        if expected == 'FEASIBLE':
            feasible[option.id] = option
            _positive_or_zero_decimal(entry.get('score'))
            with localcontext() as ctx:
                ctx.prec = 90
                total_weight = sum((c.weight for c in goal.criteria), Decimal(0))
                weighted = Decimal(0)
                for c in goal.criteria:
                    v = option.values[c.id]
                    component = ((v - c.score_min) / (c.score_max - c.score_min)
                                 if c.direction == 'max' else
                                 (c.score_max - v) / (c.score_max - c.score_min))
                    weighted += c.weight * max(Decimal(0), min(Decimal(1), component))
                raw = weighted / total_weight * 100
                expected_scores[option.id] = raw
                rounded = raw.quantize(Decimal('0.01'))
            _check(Decimal(entry['score']) == rounded, f'{option.id} 가중치 점수 불일치')
        else:
            _check(entry.get('score') is None, '제외된 후보에 점수가 붙었습니다')
    ranking, winners, frontier = (report.get(k) for k in ('ranking', 'winners', 'pareto_frontier'))
    _check(type(ranking) is list and type(winners) is list and type(frontier) is list,
           '순위 결과 형식 오류')
    _check(len(ranking) == len(feasible) and set(ranking) == set(feasible)
           and len(set(ranking)) == len(ranking), '순위에 빠지거나 추가된 후보가 있습니다')
    _check(len(winners) == len(set(winners)) and set(winners) <= set(feasible),
           '우승 후보가 평가 후보와 일치하지 않습니다')
    _check(len(frontier) == len(set(frontier)) and set(frontier) <= set(feasible),
           'Pareto 결과에 잘못된 후보가 있습니다')
    expected_frontier = {
        opt.id for opt in feasible.values() if not any(
            _dominates(other, opt, goal.criteria) for other in feasible.values() if other.id != opt.id
        )
    }
    _check(set(frontier) == expected_frontier, '원본 지표와 Pareto 판정이 맞지 않습니다')
    status = report['status']
    _check((status == 'UNAVAILABLE' and not feasible and not winners) or
           (status == 'TIE' and len(winners) >= 2 and bool(feasible)) or
           (status == 'DECIDED' and len(winners) == 1 and bool(feasible)),
           '선택 완료·동점·증거 부족 상태가 모순됩니다')
    if winners:
        _check(set(winners) <= set(ranking[:len(winners)]), '수상 후보와 순위가 맞지 않습니다')
        best_score = max(expected_scores.values())
        expected_winners = {key for key, value in expected_scores.items() if value == best_score}
        _check(set(winners) == expected_winners, '원시 정밀도 가중치 점수와 우승 후보가 다릅니다')
    _check(ranking == sorted(feasible, key=lambda k: (-expected_scores[k], k)),
           '원시 가중치 순위 불일치')
    verify_choice_display_evidence(goal, report)
    return (['schema', 'feasibility', 'ranking', 'pareto', 'detail_evidence', 'status'],
            _choice_diagnostics(goal, indexed, status))


def _verify_csv(goal: AuditGoal, report: dict) -> tuple[list[str], dict]:
    _check(report.get('plan_version') == PLAN_VERSION and report.get('goal') == 'keyed_csv_audit',
           'CSV 계획 버전 또는 범위가 잘못됐습니다')
    _check(report.get('key') == goal.key and report.get('metrics') == goal.values,
           '사용자 입력 키·지표와 결과가 다릅니다')
    _check(report.get('strategy') == ('SINGLE_RECONCILE' if len(goal.values) == 1
                                       else 'MULTI_DIAGNOSE'), '허가되지 않은 실행 전략입니다')
    sources = report.get('sources')
    _check(type(sources) is list and len(sources) == 2, '근거 파일 목록 형식이 잘못됐습니다')
    for path, source in zip((goal.left, goal.right), sources):
        _check(type(source) is dict, '원본 기록 형식 오류')
        resolved = Path(path).expanduser().resolve(strict=True)
        _check(source.get('filename') == resolved.name and source.get('sha256') == _file_digest(resolved),
               '원본 파일의 해시가 일치하지 않습니다')
    primary = report.get('primary')
    _check(type(primary) is dict and primary.get('status') == report['status'],
           '기본 검증과 최종 상태가 다릅니다')
    steps = report.get('steps')
    _check(type(steps) is list and 1 <= len(steps) <= 5 and
           steps[-1] == {'step': 'verify_receipt', 'skill': 'evidence.verify_receipt.v1', 'status': 'PASS'},
           '원본 검증 영수증이 없습니다')
    for event in steps:
        _check(type(event) is dict and event.get('skill') in {
            'csv.sha256.v1','csv.reconcile.v1','csv.diagnose.v1','csv.schema_inspect.v1',
            'evidence.verify_receipt.v1'}, '미승인 스킬 영수증이 포함됐습니다')
    status = report['status']
    if status == 'CONFLICT':
        primary_status = primary.get('status')
        _check(primary_status == 'CONFLICT', '충돌 판정 근거가 없습니다')
        if len(goal.values) == 1:
            escalation = report.get('escalation')
            _check(type(escalation) is dict and escalation.get('status') == 'CONFLICT',
                   '필수 충돌 재진단이 누락됐습니다')
        diag = {'type':'CONFLICT_REVIEW','action_required':True,
                'hint':'차이가 발생한 키·열과 허용 오차·원본 출처를 검토하세요.'}
    elif status == 'UNAVAILABLE':
        _check(type(report.get('unavailable_inspection')) is list,
               '검증 불가 상태인데 대체 열 구조 점검이 없습니다')
        diag = {'type':'SOURCE_SCHEMA_REVIEW','action_required':True,
                'hint':'입력 원본의 열 이름·숫자 형식·데이터 누락을 확인하세요.'}
    else:
        diag = {'type':'NONE','action_required':False}
    return ['plan_version','strategy','provenance','skills','status'],diag


def verify_goal_receipt(kind: str, goal: ChoiceGoal | AuditGoal | TaskGoal | ScheduleGoal | QualityGoal | DriftGoal | SqliteTableGoal | RelationshipGoal | EvidenceSearchGoal, report: object) -> dict:
    """Fail closed on inconsistent receipt; do not silently retry with weaker rules."""
    _check(kind in ALLOWED_STATUS and type(report) is dict, '지원하지 않는 판정 영수증')
    _check(report.get('status') in ALLOWED_STATUS[kind], '목표에 맞지 않는 상태 코드')
    if kind == 'choose_options':
        _check(type(goal) is ChoiceGoal, '선택지 원본 계약 오류')
        checks, diag = _verify_choice(goal, report)
    elif kind == 'csv_audit':
        _check(type(goal) is AuditGoal, 'CSV 원본 계약 오류')
        checks, diag = _verify_csv(goal, report)
    elif kind == 'plan_tasks':
        _check(type(goal) is TaskGoal, '작업 포트폴리오 원본 계약 오류')
        checks, diag = verify_task_receipt(goal, report)
    elif kind == 'schedule_tasks':
        _check(type(goal) is ScheduleGoal, '임계 경로 원본 계약 오류')
        checks, diag = verify_schedule_receipt(goal, report)
    elif kind == 'csv_quality':
        _check(type(goal) is QualityGoal, 'CSV 품질 원본 계약 오류')
        checks, diag = verify_quality_receipt(goal, report)
    elif kind == 'csv_schema_drift':
        _check(type(goal) is DriftGoal, 'CSV 스키마 원본 계약 오류')
        checks, diag = verify_drift_receipt(goal, report)
    elif kind == 'sqlite_table_audit':
        _check(type(goal) is SqliteTableGoal, 'SQLite 원본 계약 오류')
        checks, diag = verify_sqlite_receipt(goal, report)
    elif kind == 'csv_relationships':
        _check(type(goal) is RelationshipGoal, 'CSV 상관관계 원본 계약 오류')
        checks, diag = verify_relationship_receipt(goal, report)
    else:
        _check(type(goal) is EvidenceSearchGoal, '로컬 증거 검색 계약 오류')
        checks, diag = verify_search_receipt(goal, report)
    return {'version': GUARD_VERSION, 'status': 'PASS', 'checks': checks,
            'diagnostics': diag, 'policy': 'READ_ONLY;NO_REMOTE;NO_AUTOMATIC_REPAIR'}
