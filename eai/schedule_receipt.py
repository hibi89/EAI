"""Independent P11 schedule receipt guard: recursive path lengths, not CPM traversal."""
from decimal import Decimal, localcontext
from functools import lru_cache

from .analysis import _render_decimal
from .task_schedule import ScheduleGoal, SCHEDULE_VERSION, SCOPE


def verify_schedule_receipt(goal: ScheduleGoal, receipt: dict) -> tuple[list[str], dict]:
    """Recompute all path and slack values without losing 12-place decimal fractions."""
    with localcontext() as ctx:
        ctx.prec = 90
        return _verify_schedule_receipt_precise(goal, receipt)


def _verify_schedule_receipt_precise(goal: ScheduleGoal, receipt: dict) -> tuple[list[str], dict]:
    if type(goal) is not ScheduleGoal or type(receipt) is not dict:
        raise ValueError('EAI 영수증 검증 실패: invalid schedule receipt')
    data = {item.id: item for item in goal.tasks}
    children = {name: set() for name in data}
    for item in goal.tasks:
        for dependency in item.requires:
            children[dependency].add(item.id)

    @lru_cache(maxsize=32)
    def before(task_id):
        item = data[task_id]
        return max((before(d) + data[d].hours for d in item.requires), default=Decimal(0))

    @lru_cache(maxsize=32)
    def after(task_id):
        return max((data[s].hours + after(s) for s in children[task_id]), default=Decimal(0))

    @lru_cache(maxsize=32)
    def paths(task_id):
        item = data[task_id]
        if not item.requires:
            return (task_id,)
        max_before = before(task_id)
        return min(paths(dep) for dep in item.requires
                   if before(dep) + data[dep].hours == max_before) + (task_id,)

    minimum = max(before(name) + item.hours for name, item in data.items())
    eligible_end = [name for name, item in data.items()
                    if before(name) + item.hours == minimum]
    representative_path = list(min(paths(name) for name in eligible_end))
    rows = []
    critical = []
    for task_id in sorted(data):
        item = data[task_id]
        earliest_start = before(task_id)
        latest_finish = minimum - after(task_id)
        latest_start = latest_finish - item.hours
        slack = latest_start - earliest_start
        if slack == 0:
            critical.append(task_id)
        rows.append({'id': task_id,'hours':_render_decimal(item.hours),
                     'requires':list(item.requires),
                     'earliest_start':_render_decimal(earliest_start),
                     'earliest_finish':_render_decimal(earliest_start + item.hours),
                     'latest_start':_render_decimal(latest_start),
                     'latest_finish':_render_decimal(latest_finish),
                     'slack':_render_decimal(slack), 'is_critical': slack == 0})
    status = 'DECIDED' if minimum <= goal.deadline_hours else 'UNAVAILABLE'
    expected = {'plan_version':SCHEDULE_VERSION,'kind':'schedule_tasks','goal':goal.goal,
                'status':status,'deadline_hours':_render_decimal(goal.deadline_hours),
                'minimum_finish_hours':_render_decimal(minimum),
                'deadline_margin_hours':_render_decimal(goal.deadline_hours - minimum),
                'critical_path':representative_path,'critical_tasks':critical,
                'ready_tasks':sorted(item.id for item in goal.tasks if not item.requires),
                'tasks':rows,'scope':SCOPE}
    if receipt != expected:
        raise ValueError('EAI 영수증 검증 실패: schedule critical path, timing or deadline mismatch')
    diagnostic = ({'type':'DEADLINE_EXCEEDED','action_required':True,
                   'hint':'현재 선행조건·작업시간에서는 마감 초과입니다. 입력 추정치나 마감을 검토하세요. '
                          'EAI는 요구사항을 임의로 수정하지 않습니다.'}
                  if status == 'UNAVAILABLE' else
                  {'type':'NONE','action_required':False})
    return ['schema','dependencies','earliest_latest','critical_path','deadline','status'], diagnostic
