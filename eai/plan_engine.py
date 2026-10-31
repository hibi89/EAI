"""P6 CPU-owned bounded goal planner and verified execution receipts.

Only fixed, read-only skills are available. No generated Python, shell, network,
Qwen solution text, implicit file discovery, database or original CSV writes.
"""
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from .csv_analysis import inspect_csv
from .diagnose_csv import MAX_METRICS, _validate, diagnose_csv
from .reconcile_csv import reconcile_csv
from .verify_csv import _file_digest


PLAN_VERSION = 'eai.goal.csv_audit.v1'
MAX_STEP_EVENTS = 5
ALLOWED_SKILLS = frozenset({
    'csv.sha256.v1', 'csv.reconcile.v1', 'csv.diagnose.v1',
    'csv.schema_inspect.v1', 'evidence.verify_receipt.v1',
})


@dataclass(frozen=True)
class AuditGoal:
    left: str | Path
    right: str | Path
    key: str
    values: list[str]
    tolerance: str = '0'
    encoding: str = 'utf-8-sig'
    max_seconds: int = 60


@dataclass(frozen=True)
class PlannedStep:
    name: str
    skill: str
    when: str


@dataclass(frozen=True)
class AuditPlan:
    version: str
    strategy: str
    steps: tuple[PlannedStep, ...]


class RuleGoalPlanner:
    """EAI owns branching decisions; user data never becomes executable code."""

    def compile(self, goal: AuditGoal) -> AuditPlan:
        if type(goal) is not AuditGoal:
            raise ValueError('지원되지 않는 목표 형식입니다.')
        if type(goal.max_seconds) is not int or not 1 <= goal.max_seconds <= 120:
            raise ValueError('최대 실행 시간은 1~120초입니다.')
        _validate(goal.key, goal.values, goal.tolerance, goal.encoding)
        if len(goal.values) > MAX_METRICS:
            raise ValueError('지표 개수 제한을 초과했습니다.')
        strategy = 'SINGLE_RECONCILE' if len(goal.values) == 1 else 'MULTI_DIAGNOSE'
        primary = 'csv.reconcile.v1' if len(goal.values) == 1 else 'csv.diagnose.v1'
        steps = (
            PlannedStep('anchor_sources', 'csv.sha256.v1', 'always'),
            PlannedStep('primary_solve', primary, 'always'),
            PlannedStep('conflict_escalation', 'csv.diagnose.v1',
                        'single_metric_and_conflict'),
            PlannedStep('unavailable_fallback', 'csv.schema_inspect.v1',
                        'primary_unavailable'),
            PlannedStep('verify_receipt', 'evidence.verify_receipt.v1', 'always'),
        )
        if len(steps) > MAX_STEP_EVENTS or not all(s.skill in ALLOWED_SKILLS for s in steps):
            raise RuntimeError('승인되지 않은 계획 단계')
        return AuditPlan(PLAN_VERSION, strategy, steps)


class CPUPlanExecutor:
    """Runs a precompiled plan of fixed read-only skills and checks evidence."""

    def __init__(self, planner: RuleGoalPlanner | None = None):
        self.planner = planner or RuleGoalPlanner()

    @staticmethod
    def _resolve_sources(goal: AuditGoal) -> tuple[Path, Path]:
        left = Path(goal.left).expanduser().resolve(strict=True)
        right = Path(goal.right).expanduser().resolve(strict=True)
        if left == right:
            raise ValueError('동일한 CSV 경로 두 개를 사용할 수 없습니다.')
        return left, right

    @staticmethod
    def _inspect(left: Path, right: Path, encoding: str) -> list[dict]:
        result = []
        for path in (left, right):
            profile = inspect_csv(path, encoding=encoding)
            result.append({
                'filename': path.name, 'rows': profile['rows'],
                'columns': [{'name': s['name'], 'type': s['type']} for s in profile['stats']],
            })
        return result

    @staticmethod
    def _verify_receipt(primary: dict, anchored: list[dict], left: Path, right: Path) -> None:
        before = [s['sha256'] for s in anchored]
        after = [_file_digest(left), _file_digest(right)]
        if before != after:
            raise ValueError('검증 도중 원본 CSV가 변경되어 결과를 무효화했습니다.')
        recorded = [s['sha256'] for s in primary['sources']]
        if recorded != before:
            raise ValueError('실행 결과의 원본 해시가 실제 입력과 다릅니다.')

    def execute(self, goal: AuditGoal) -> dict:
        plan = self.planner.compile(goal)
        left, right = self._resolve_sources(goal)
        started = monotonic()
        events: list[dict] = []

        def enforce_budget() -> None:
            # This bounds admission to each stage, NOT a mid-stage hard interrupt.
            if monotonic() - started >= goal.max_seconds:
                raise TimeoutError('단계 시작 전 실행 시간 예산을 초과했습니다.')

        def note(name: str, skill: str, status: str) -> None:
            if skill not in ALLOWED_SKILLS:
                raise PermissionError('승인되지 않은 외부 실행 기능을 차단했습니다.')
            if len(events) >= MAX_STEP_EVENTS:
                raise RuntimeError('최대 실행 단계 수를 초과했습니다.')
            events.append({'step': name, 'skill': skill, 'status': status})

        enforce_budget()
        a, b = _file_digest(left), _file_digest(right)
        anchored = [{'filename': left.name, 'sha256': a},
                    {'filename': right.name, 'sha256': b}]
        note('anchor_sources', 'csv.sha256.v1', 'DONE')

        enforce_budget()
        if plan.strategy == 'SINGLE_RECONCILE':
            primary = reconcile_csv(left, right, key=goal.key, value=goal.values[0],
                                    tolerance=goal.tolerance, encoding=goal.encoding)
            if primary['status'] == 'AGREE' and primary['counts']['agree'] == 0:
                # No matched numeric observations is NOT evidence of agreement.
                primary = dict(primary, status='UNAVAILABLE', warnings=[
                    *primary['warnings'], '일치한 숫자 행이 없어 합치 판정을 보류합니다.'])
            primary_skill = 'csv.reconcile.v1'
        else:
            primary = diagnose_csv(left, right, key=goal.key, values=goal.values,
                                   tolerance=goal.tolerance, encoding=goal.encoding)
            primary_skill = 'csv.diagnose.v1'
        status = primary['status']
        note('primary_solve', primary_skill, status)
        escalation = None
        inspection = None

        if status == 'CONFLICT' and plan.strategy == 'SINGLE_RECONCILE':
            enforce_budget()
            escalation = diagnose_csv(left, right, key=goal.key, values=goal.values,
                                      tolerance=goal.tolerance, encoding=goal.encoding)
            if escalation['status'] != 'CONFLICT':
                raise ValueError('대체 진단과 기본 판정의 결과가 충돌합니다.')
            note('conflict_escalation', 'csv.diagnose.v1', escalation['status'])
        elif status == 'UNAVAILABLE':
            enforce_budget()
            inspection = self._inspect(left, right, goal.encoding)
            note('unavailable_fallback', 'csv.schema_inspect.v1', 'DONE')

        enforce_budget()
        self._verify_receipt(primary, anchored, left, right)
        if escalation is not None and ([s['sha256'] for s in escalation['sources']] != [a, b]):
            raise ValueError('대체 진단의 원본 해시가 다릅니다.')
        note('verify_receipt', 'evidence.verify_receipt.v1', 'PASS')
        return {
            'plan_version': plan.version, 'goal': 'keyed_csv_audit',
            'strategy': plan.strategy, 'status': status,
            'sources': anchored, 'key': goal.key, 'metrics': list(goal.values),
            'steps': events,
            'plan': [{'step': p.name, 'skill': p.skill, 'when': p.when}
                     for p in plan.steps],
            'primary': primary,
            'escalation': escalation,
            'unavailable_inspection': inspection,
            'scope': ('EAI의 CPU 코드가 명시된 두 CSV 내부 값을 비교했습니다. 원본의 진실성, '
                      '불일치의 실제 원인, 데이터 출처의 독립성은 입증하지 않았습니다. '
                      '단계별 시간 예산은 사전 검사이고 실행 중 강제 중단 기능은 아닙니다.'),
        }


def render_plan_report(report: dict) -> str:
    lines = [f"EAI P6 독립 계획 실행: {report['status']}",
             f"선택된 경로: {report['strategy']}"]
    for step in report['steps']:
        lines.append(f"{step['step']} / {step['skill']}: {step['status']}")
    if report['escalation'] is not None:
        lines.append('충돌 세부 진단 경로를 추가 실행했습니다.')
        for item in report['escalation']['candidates'][:5]:
            lines.append(f"후보 키: {item['key']} / {item['hypothesis_code']}")
    if report['unavailable_inspection'] is not None:
        lines.append('기본 검증이 불가능해 CSV 열 구조를 점검했습니다.')
        for item in report['unavailable_inspection']:
            lines.append(f"{item['filename']}: " + ', '.join(
                f"{col['name']}({col['type']})" for col in item['columns']))
    lines.append(report['scope'])
    return '\n'.join(lines)
