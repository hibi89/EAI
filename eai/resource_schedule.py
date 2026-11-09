"""P21 exact bounded resource-constrained task scheduling, CPU-only."""
from dataclasses import dataclass
from pathlib import Path

from .decision_engine import ID_RE

VERSION = "eai.goal.resource_schedule.v1"
MAX_STATES = 100000
SCOPE = (
    "명시된 정수 시간 슬롯·자원 용량·선행관계에서 가능한 최소 완료시간을 탐색했습니다. "
    "실제 사람/장비 예약, 파일 수정, 캘린더 등록, 결제 또는 작업 실행은 하지 않습니다. "
    "모든 작업은 쪼갤 수 없는 시간 단위로 간주하며, 최대 탐색 상태 수를 초과하면 "
    "최적해를 주장하지 않고 오류로 중단합니다."
)


@dataclass(frozen=True)
class Task:
    id: str
    hours: int
    requires: tuple[str, ...]
    resources: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ResourceGoal:
    goal: str
    horizon_hours: int
    capacities: tuple[tuple[str, int], ...]
    tasks: tuple[Task, ...]


def _valid_id(value: object) -> bool:
    return type(value) is str and bool(ID_RE.fullmatch(value))


def validate_resource_goal(raw: object) -> ResourceGoal:
    mandatory = {"version", "kind", "goal", "horizon_hours", "capacities", "tasks"}
    if type(raw) is not dict or set(raw) != mandatory or type(raw["version"]) is not int or (
        raw["version"] != 1 or raw["kind"] != "resource_schedule"
    ):
        raise ValueError("invalid versioned resource_schedule contract")
    name = raw["goal"]
    if type(name) is not str or not 1 <= len(name.strip()) <= 120 or any(
        ord(ch) < 32 for ch in name
    ):
        raise ValueError("invalid resource planning goal title")
    horizon = raw["horizon_hours"]
    if type(horizon) is not int or not 1 <= horizon <= 24:
        raise ValueError("resource schedule horizon must be 1-24 integer hours")
    capacities = raw["capacities"]
    if type(capacities) is not dict or not 1 <= len(capacities) <= 3 or any(
        not _valid_id(key) or type(value) is not int or not 1 <= value <= 4
        for key, value in capacities.items()
    ):
        raise ValueError("resource schedule requires 1-3 bounded capacities")
    items = raw["tasks"]
    if type(items) is not list or not 2 <= len(items) <= 7:
        raise ValueError("resource schedule requires 2-7 tasks")
    tasks, used = [], set()
    for item in items:
        if type(item) is not dict or set(item) != {"id", "hours", "requires", "resources"}:
            raise ValueError("resource task contract malformed")
        name = item["id"]
        hours = item["hours"]
        deps = item["requires"]
        demand = item["resources"]
        if not _valid_id(name) or name in used:
            raise ValueError("invalid/duplicate resource task ID")
        if type(hours) is not int or not 1 <= hours <= 8:
            raise ValueError("task duration must be 1-8 integer hours")
        if type(deps) is not list or len(deps) > 6 or any(
            not _valid_id(d) for d in deps
        ) or len(set(deps)) != len(deps):
            raise ValueError("invalid task predecessor IDs")
        if type(demand) is not dict or not 1 <= len(demand) <= len(capacities) or any(
            key not in capacities or type(amount) is not int or
            not 1 <= amount <= capacities[key] for key, amount in demand.items()
        ):
            raise ValueError("task resource requirements exceed available capacities")
        used.add(name)
        tasks.append(Task(name, hours, tuple(sorted(deps)),
                          tuple(sorted(demand.items()))))
    lookup = {task.id: task for task in tasks}
    if any(task.id in task.requires or any(dep not in lookup for dep in task.requires)
           for task in tasks):
        raise ValueError("task has unknown or self dependency")
    pending, finished, ordered = set(lookup), set(), []
    while pending:
        ready = sorted(name for name in pending if set(lookup[name].requires) <= finished)
        if not ready:
            raise ValueError("cyclic resource scheduling dependencies")
        ordered.extend(ready)
        pending -= set(ready)
        finished.update(ready)
    return ResourceGoal(raw["goal"].strip(), horizon, tuple(sorted(capacities.items())),
                        tuple(lookup[name] for name in ordered))


def _lower_bound(goal: ResourceGoal) -> int:
    end = {}
    for task in goal.tasks:
        end[task.id] = task.hours + max(
            (end[x] for x in task.requires), default=0
        )
    capacities = dict(goal.capacities)
    resource_bound = max(
        (sum(task.hours * dict(task.resources).get(name, 0)
             for task in goal.tasks) + cap - 1) // cap
        for name, cap in capacities.items()
    )
    return max(max(end.values()), resource_bound)


def _find_schedule(goal: ResourceGoal, horizon: int, budget: list[int]) -> dict | None:
    caps = dict(goal.capacities)
    occupancy = {name: [0] * horizon for name in caps}
    starts, ends = {}, {}
    tasks = goal.tasks

    def explore(index):
        budget[0] += 1
        if budget[0] > MAX_STATES:
            raise ValueError("resource schedule complexity budget exhausted")
        if index == len(tasks):
            return dict(starts)
        task = tasks[index]
        earliest = max((ends[dep] for dep in task.requires), default=0)
        for start in range(earliest, horizon - task.hours + 1):
            fits = all(
                all(occupancy[name][hour] + amount <= caps[name]
                    for hour in range(start, start + task.hours))
                for name, amount in task.resources
            )
            if not fits:
                continue
            starts[task.id] = start
            ends[task.id] = start + task.hours
            for name, amount in task.resources:
                for hour in range(start, start + task.hours):
                    occupancy[name][hour] += amount
            solution = explore(index + 1)
            if solution is not None:
                return solution
            for name, amount in task.resources:
                for hour in range(start, start + task.hours):
                    occupancy[name][hour] -= amount
            starts.pop(task.id)
            ends.pop(task.id)
        return None
    return explore(0)


def execute_resource_goal(goal: ResourceGoal) -> dict:
    if type(goal) is not ResourceGoal:
        raise ValueError("unvalidated resource schedule")
    lower = _lower_bound(goal)
    attempts = [0]
    selected = None
    duration = None
    for finish in range(lower, goal.horizon_hours + 1):
        possible = _find_schedule(goal, finish, attempts)
        if possible is not None:
            duration, selected = finish, possible
            break
    tasks = [] if selected is None else [
        {"id": t.id, "start": selected[t.id], "end": selected[t.id] + t.hours}
        for t in goal.tasks
    ]
    return {
        "version": VERSION, "kind": "resource_schedule", "goal": goal.goal,
        "status": "DECIDED" if selected is not None else "UNAVAILABLE",
        "horizon_hours": goal.horizon_hours,
        "capacities": dict(goal.capacities),
        "tasks_contract": [
            {"id": t.id, "hours": t.hours, "requires": list(t.requires),
             "resources": dict(t.resources)} for t in goal.tasks
        ],
        "minimum_lower_bound": lower, "makespan": duration,
        "slack_hours": None if duration is None else goal.horizon_hours - duration,
        "schedule": tasks, "scope": SCOPE
    }


def render_resource_plan(report: dict) -> str:
    lines = ["EAI 용량 제약 일정 계획: " + report["status"],
             f"하한 {report['minimum_lower_bound']}시간 / "
             f"계획 완료 {report['makespan']}시간"]
    for item in report["schedule"]:
        lines.append(f"{item['id']}: {item['start']} ~ {item['end']}시간")
    return "\n".join(lines + [report["scope"]])
