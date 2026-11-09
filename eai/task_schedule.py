"""P11 deterministic critical-path analysis from explicit local task dependencies.

This is CPM under unlimited parallel capacity, not a worker-constrained schedule.
It does not perform tasks, infer actual durations or contact any external service.
"""
from dataclasses import dataclass
from decimal import Decimal

from .analysis import _render_decimal
from .decision_engine import ID_RE, _num

SCHEDULE_VERSION = 'eai.goal.schedule_tasks.v1'
MAX_SCHEDULE_TASKS = 24
SCOPE = (
    '선행조건과 사용자 입력 소요시간을 기준으로 병렬 인력 제한이 없는 CPM 계산만 수행했습니다. '
    '실제 인원·근무시간·휴일·변동성·자원 충돌·입력 추정치의 정확도는 반영하지 않습니다. '
    '작업을 실행하거나 자동으로 일정을 변경하지 않습니다.'
)


@dataclass(frozen=True)
class ScheduleTask:
    id: str
    hours: Decimal
    requires: tuple[str, ...]


@dataclass(frozen=True)
class ScheduleGoal:
    goal: str
    deadline_hours: Decimal
    tasks: tuple[ScheduleTask, ...]


def validate_schedule_goal(raw: object) -> ScheduleGoal:
    """Fail closed on extra instructions, cycles, unknown dependencies and floats."""
    required = {'version', 'kind', 'goal', 'deadline_hours', 'tasks'}
    if type(raw) is not dict or set(raw) != required:
        raise ValueError('schedule_tasks requires fixed versioned attributes')
    if type(raw['version']) is not int or raw['version'] != 1 or raw['kind'] != 'schedule_tasks':
        raise ValueError('unsupported schedule_tasks version')
    title = raw['goal']
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(ord(c) < 32 for c in title):
        raise ValueError('invalid schedule title')
    deadline = _num(raw['deadline_hours'], 'deadline_hours')
    if deadline < 0:
        raise ValueError('deadline_hours cannot be negative')
    originals = raw['tasks']
    if type(originals) is not list or not 1 <= len(originals) <= MAX_SCHEDULE_TASKS:
        raise ValueError('schedule_tasks supports 1-24 tasks')
    tasks, seen = [], set()
    for item in originals:
        if type(item) is not dict or set(item) != {'id', 'hours', 'requires'}:
            raise ValueError('task must specify id, hours and requires only')
        task_id = item['id']
        if type(task_id) is not str or not ID_RE.fullmatch(task_id) or task_id in seen:
            raise ValueError('invalid or duplicate schedule task id')
        seen.add(task_id)
        hours = _num(item['hours'], 'task.hours')
        if hours < 0:
            raise ValueError('task hours cannot be negative')
        requires = item['requires']
        if type(requires) is not list or len(requires) > MAX_SCHEDULE_TASKS or any(
            type(dep) is not str or not ID_RE.fullmatch(dep) for dep in requires
        ):
            raise ValueError('invalid schedule dependencies')
        if len(set(requires)) != len(requires):
            raise ValueError('duplicate schedule dependencies')
        tasks.append(ScheduleTask(task_id, hours, tuple(sorted(requires))))
    graph = {task.id: task.requires for task in tasks}
    if any(task.id in task.requires or any(dep not in graph for dep in task.requires) for task in tasks):
        raise ValueError('unknown or self schedule dependency')
    active, checked = set(), set()

    def visit(task_id: str) -> None:
        if task_id in active:
            raise ValueError('cyclic schedule dependencies')
        if task_id in checked:
            return
        active.add(task_id)
        for dep in graph[task_id]:
            visit(dep)
        active.remove(task_id)
        checked.add(task_id)

    for task_id in graph:
        visit(task_id)
    return ScheduleGoal(title.strip(), deadline, tuple(tasks))


def execute_schedule_goal(goal: ScheduleGoal) -> dict:
    """Forward/backward CPM over a bounded DAG with exact Decimal arithmetic."""
    if type(goal) is not ScheduleGoal:
        raise ValueError('unvalidated schedule goal')
    lookup = {task.id: task for task in goal.tasks}
    done = set()
    order = []
    starts, finishes, longest_paths = {}, {}, {}
    while len(done) < len(lookup):
        ready = sorted(task_id for task_id, task in lookup.items()
                       if task_id not in done and set(task.requires).issubset(done))
        if not ready:
            raise ValueError('schedule dependencies could not be resolved')
        for task_id in ready:
            item = lookup[task_id]
            start = max((finishes[x] for x in item.requires), default=Decimal(0))
            if item.requires:
                candidate_paths = [longest_paths[x] for x in item.requires if finishes[x] == start]
                path = min(candidate_paths) + (task_id,)
            else:
                path = (task_id,)
            starts[task_id] = start
            finishes[task_id] = start + item.hours
            longest_paths[task_id] = path
            order.append(task_id)
            done.add(task_id)
    makespan = max(finishes.values())
    successors = {task_id: [] for task_id in lookup}
    for task in lookup.values():
        for prerequisite in task.requires:
            successors[prerequisite].append(task.id)
    latest_starts, latest_finishes = {}, {}
    for task_id in reversed(order):
        finish = min((latest_starts[x] for x in successors[task_id]), default=makespan)
        latest_finishes[task_id] = finish
        latest_starts[task_id] = finish - lookup[task_id].hours
    tasks = []
    for task_id in sorted(lookup):
        item = lookup[task_id]
        slack = latest_starts[task_id] - starts[task_id]
        tasks.append({'id': task_id, 'hours': _render_decimal(item.hours),
                      'requires': list(item.requires),
                      'earliest_start': _render_decimal(starts[task_id]),
                      'earliest_finish': _render_decimal(finishes[task_id]),
                      'latest_start': _render_decimal(latest_starts[task_id]),
                      'latest_finish': _render_decimal(latest_finishes[task_id]),
                      'slack': _render_decimal(slack), 'is_critical': slack == 0})
    end_tasks = [task_id for task_id, value in finishes.items() if value == makespan]
    critical_path = list(min(longest_paths[task_id] for task_id in end_tasks))
    status = 'DECIDED' if makespan <= goal.deadline_hours else 'UNAVAILABLE'
    return {'plan_version': SCHEDULE_VERSION, 'kind': 'schedule_tasks', 'goal': goal.goal,
            'status': status, 'deadline_hours': _render_decimal(goal.deadline_hours),
            'minimum_finish_hours': _render_decimal(makespan),
            'deadline_margin_hours': _render_decimal(goal.deadline_hours - makespan),
            'critical_path': critical_path,
            'critical_tasks': sorted(row['id'] for row in tasks if row['is_critical']),
            'ready_tasks': sorted(task.id for task in goal.tasks if not task.requires),
            'tasks': tasks, 'scope': SCOPE}


def render_schedule(report: dict) -> str:
    lines = [f"EAI 독립 임계 경로 일정: {report['status']}",
             f"목표: {report['goal']}",
             f"최소 완료시간(무제한 병렬 가정): {report['minimum_finish_hours']}시간",
             f"마감 상한: {report['deadline_hours']}시간 / 여유: {report['deadline_margin_hours']}시간",
             '대표 임계 경로: ' + ' → '.join(report['critical_path']),
             '임계 작업: ' + ', '.join(report['critical_tasks'])]
    if report['status'] == 'UNAVAILABLE':
        lines.append('마감 초과: 현재 의존성과 입력시간으로는 마감을 충족할 수 없습니다.')
    for row in report['tasks']:
        lines.append(f"{row['id']}: {row['earliest_start']}~{row['earliest_finish']}시간 "
                     f"(여유 {row['slack']}, {'임계' if row['is_critical'] else '비임계'})")
    lines.append(report['scope'])
    return '\n'.join(lines)
