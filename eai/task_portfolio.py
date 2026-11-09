"""P10 bounded exact offline task-portfolio planning, with independently checked receipt."""
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from .analysis import _render_decimal
from .decision_engine import ID_RE, _num

TASK_VERSION = 'eai.goal.plan_tasks.v1'
MAX_TASKS = 12
MAX_PREVIEW = 8
SCOPE = ('사용자가 입력한 시간·비용·가치와 선행조건만 최적화합니다. '
         '실제 소요시간·가치·시장 사실은 검증하지 않으며 작업 실행/지출/업로드는 없습니다.')


@dataclass(frozen=True)
class Task:
    id: str
    hours: Decimal
    cost: Decimal
    value: Decimal
    requires: tuple[str, ...]


@dataclass(frozen=True)
class TaskGoal:
    goal: str
    max_hours: Decimal
    max_cost: Decimal
    tasks: tuple[Task, ...]


def validate_task_goal(raw: object) -> TaskGoal:
    if type(raw) is not dict or set(raw) != {'version','kind','goal','max_hours','max_cost','tasks'}:
        raise ValueError('unsupported plan_tasks attributes')
    if type(raw['version']) is not int or raw['version'] != 1 or raw['kind'] != 'plan_tasks':
        raise ValueError('unsupported task goal version')
    title = raw['goal']
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(ord(c) < 32 for c in title):
        raise ValueError('invalid task goal')
    hours, cost = _num(raw['max_hours'], 'max_hours'), _num(raw['max_cost'], 'max_cost')
    if hours < 0 or cost < 0:
        raise ValueError('negative budget')
    raw_tasks = raw['tasks']
    if type(raw_tasks) is not list or not 1 <= len(raw_tasks) <= MAX_TASKS:
        raise ValueError('1-12 tasks required')
    tasks, names = [], set()
    for item in raw_tasks:
        if type(item) is not dict or set(item) != {'id','hours','cost','value','requires'}:
            raise ValueError('invalid task attributes')
        tid = item['id']
        if type(tid) is not str or not ID_RE.fullmatch(tid) or tid in names:
            raise ValueError('invalid or duplicate task ID')
        names.add(tid)
        h, c, v = (_num(item[key], key) for key in ('hours','cost','value'))
        if min(h, c, v) < 0:
            raise ValueError('negative task resource or value')
        req = item['requires']
        if type(req) is not list or len(req) > MAX_TASKS or len(set(map(str,req))) != len(req) or any(
            type(x) is not str or not ID_RE.fullmatch(x) for x in req
        ):
            raise ValueError('invalid dependencies')
        tasks.append(Task(tid, h, c, v, tuple(req)))
    graph = {t.id: t.requires for t in tasks}
    if any(t.id in t.requires or any(x not in names for x in t.requires) for t in tasks):
        raise ValueError('unknown or self dependency')
    active, visited = set(), set()
    def visit(tid):
        if tid in active:
            raise ValueError('cyclic task dependencies')
        if tid in visited:
            return
        active.add(tid)
        for dep in graph[tid]:
            visit(dep)
        active.remove(tid)
        visited.add(tid)
    for tid in graph:
        visit(tid)
    return TaskGoal(title.strip(), hours, cost, tuple(tasks))


def execute_task_goal(goal: TaskGoal) -> dict:
    """Enumerate at most 4095 nonempty subsets; exact Decimal, no side effects."""
    if type(goal) is not TaskGoal:
        raise ValueError('unvalidated task goal')
    n = len(goal.tasks)
    indices = {t.id: i for i, t in enumerate(goal.tasks)}
    needed = [sum(1 << indices[dep] for dep in task.requires) for task in goal.tasks]
    max_value, winners = Decimal(0), []
    for mask in range(1, 1 << n):
        if any((mask & (1 << i)) and (mask & needed[i]) != needed[i] for i in range(n)):
            continue
        chosen = [task for i, task in enumerate(goal.tasks) if mask & (1 << i)]
        h = sum((task.hours for task in chosen), Decimal(0))
        c = sum((task.cost for task in chosen), Decimal(0))
        if h > goal.max_hours or c > goal.max_cost:
            continue
        v = sum((task.value for task in chosen), Decimal(0))
        if v <= 0:
            continue
        row = {'tasks':sorted(task.id for task in chosen), 'hours':_render_decimal(h),
               'cost':_render_decimal(c), 'value':_render_decimal(v)}
        if v > max_value:
            max_value, winners = v, [row]
        elif v == max_value:
            winners.append(row)
    winners.sort(key=lambda x:tuple(x['tasks']))
    status = 'UNAVAILABLE' if not winners else 'TIE' if len(winners) > 1 else 'DECIDED'
    return {'plan_version':TASK_VERSION, 'kind':'plan_tasks','goal':goal.goal, 'status':status,
            'max_hours':_render_decimal(goal.max_hours), 'max_cost':_render_decimal(goal.max_cost),
            'best_value':_render_decimal(max_value),
            'selected':winners[0]['tasks'] if status == 'DECIDED' else [],
            'candidate_count':len(winners), 'candidates':winners[:MAX_PREVIEW],
            'evaluated_subsets':(1 << n)-1, 'scope':SCOPE}


def verify_task_receipt(goal: TaskGoal, report: dict) -> tuple[list[str], dict]:
    """Independent combinations enumeration rechecks optimality, ties, budgets and receipt."""
    if type(goal) is not TaskGoal or type(report) is not dict:
        raise ValueError('EAI 영수증 검증 실패: invalid task receipt')
    best, candidates = Decimal(0), []
    for count in range(1, len(goal.tasks)+1):
        for subset in combinations(goal.tasks, count):
            names = {t.id for t in subset}
            if any(not set(t.requires).issubset(names) for t in subset):
                continue
            h = sum((t.hours for t in subset), Decimal(0))
            c = sum((t.cost for t in subset), Decimal(0))
            if h > goal.max_hours or c > goal.max_cost:
                continue
            v = sum((t.value for t in subset), Decimal(0))
            if v <= 0:
                continue
            row = {'tasks':sorted(names),'hours':_render_decimal(h),
                   'cost':_render_decimal(c),'value':_render_decimal(v)}
            if v > best:
                best, candidates = v, [row]
            elif v == best:
                candidates.append(row)
    candidates.sort(key=lambda x:tuple(x['tasks']))
    status = 'UNAVAILABLE' if not candidates else 'TIE' if len(candidates)>1 else 'DECIDED'
    expected = {'plan_version':TASK_VERSION, 'kind':'plan_tasks','goal':goal.goal, 'status':status,
                'max_hours':_render_decimal(goal.max_hours),'max_cost':_render_decimal(goal.max_cost),
                'best_value':_render_decimal(best),
                'selected':candidates[0]['tasks'] if status == 'DECIDED' else [],
                'candidate_count':len(candidates),'candidates':candidates[:MAX_PREVIEW],
                'evaluated_subsets':(1 << len(goal.tasks))-1,'scope':SCOPE}
    if report != expected:
        raise ValueError('EAI 영수증 검증 실패: task optimum/resources/trace mismatch')
    if status == 'UNAVAILABLE':
        diag = {'type':'NO_FEASIBLE_POSITIVE_PLAN', 'action_required':True,
                'hint':'가치가 양수인 실행가능한 조합이 없습니다. 제약을 임의로 완화하지 않습니다.'}
    elif status == 'TIE':
        diag = {'type':'TIE_REVIEW','action_required':True,
                'hint':'동점 작업 조합을 사용자가 선택해야 합니다.'}
    else:
        diag = {'type':'NONE','action_required':False}
    return ['schema','budget','dependencies','exact_optimum','ties','status'], diag


def render_task_plan(report: dict) -> str:
    result = [f"EAI 작업 포트폴리오: {report['status']}",
              f"목표: {report['goal']}",
              f"시간 한도: {report['max_hours']}, 비용 한도: {report['max_cost']}",
              f"최적 입력 가치: {report['best_value']}"]
    if report['status'] == 'DECIDED':
        result.append('선택: ' + ', '.join(report['selected']))
    elif report['status'] == 'TIE':
        result.append(f"동점 {report['candidate_count']}개: 선택 보류")
        result.extend('후보: ' + ', '.join(x['tasks']) for x in report['candidates'])
    else:
        result.append('실행가능한 양의 가치 작업 조합 없음. 결정 보류.')
    result.append(report['scope'])
    return '\n'.join(result)
