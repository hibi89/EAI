"""P21 independent resource-constraint and optimality receipt checker."""
from .resource_schedule import ResourceGoal, VERSION, SCOPE, MAX_STATES


def _bound(goal: ResourceGoal) -> int:
    # Separately reconstruct the critical path and cumulative capacity bounds.
    finishes = {}
    for task in goal.tasks:
        finishes[task.id] = task.hours + max(
            [finishes[parent] for parent in task.requires] or [0])
    capacities = dict(goal.capacities)
    pressure = []
    for name, capacity in capacities.items():
        demand = sum(t.hours * dict(t.resources).get(name, 0)
                     for t in goal.tasks)
        pressure.append((demand + capacity - 1) // capacity)
    return max([*finishes.values(), *pressure])


def _exists(goal: ResourceGoal, limit: int) -> bool:
    """Independent interval-overlap search, not primary slot-grid algorithm."""
    if limit < _bound(goal):
        return False
    tasks = goal.tasks
    cap = dict(goal.capacities)
    starts = {}
    states = [0]
    def dfs(index):
        states[0] += 1
        if states[0] > MAX_STATES:
            raise ValueError("resource receipt proof budget exhausted")
        if index == len(tasks):
            return True
        task = tasks[index]
        chosen = {previous.id: previous for previous in tasks[:index]}
        earliest = max((starts[parent] + chosen[parent].hours
                        for parent in task.requires), default=0)
        for start in range(earliest, limit - task.hours + 1):
            available = True
            for resource, demand in task.resources:
                for hour in range(start, start + task.hours):
                    concurrent = demand + sum(
                        dict(other.resources).get(resource, 0)
                        for other in tasks[:index] if other.id in starts
                        and starts[other.id] <= hour < starts[other.id] + other.hours
                    )
                    if concurrent > cap[resource]:
                        available = False
                        break
                if not available:
                    break
            if available:
                starts[task.id] = start
                if dfs(index + 1):
                    return True
                del starts[task.id]
        return False
    return dfs(0)


def verify_resource_receipt(goal: ResourceGoal, report: object) -> tuple[list[str], dict]:
    if type(goal) is not ResourceGoal or type(report) is not dict:
        raise ValueError("resource scheduling receipt invalid")
    expected_keys = {
        "version", "kind", "goal", "status", "horizon_hours", "capacities",
        "tasks_contract", "minimum_lower_bound", "makespan", "slack_hours",
        "schedule", "scope"
    }
    contract = [
        {"id": task.id, "hours": task.hours, "requires": list(task.requires),
         "resources": dict(task.resources)} for task in goal.tasks
    ]
    if set(report) != expected_keys or (
        report["version"] != VERSION or report["kind"] != "resource_schedule"
        or report["goal"] != goal.goal or report["scope"] != SCOPE
        or report["horizon_hours"] != goal.horizon_hours
        or report["capacities"] != dict(goal.capacities)
        or report["tasks_contract"] != contract
        or report["minimum_lower_bound"] != _bound(goal)
    ):
        raise ValueError("resource receipt provenance or rule mismatch")
    status = report["status"]
    if status == "UNAVAILABLE":
        if report["schedule"] != [] or report["makespan"] is not None or (
            report["slack_hours"] is not None
        ):
            raise ValueError("resource receipt unavailable status contradiction")
        if _exists(goal, goal.horizon_hours):
            raise ValueError("resource receipt false unavailable status")
        diagnostic = {
            "type": "RESOURCE_CAPACITY_OR_DEADLINE",
            "action_required": True,
            "hint": "자원 용량·작업 의존관계·제한시간을 검토하세요."
        }
    elif status == "DECIDED":
        tasks = report["schedule"]
        if type(tasks) is not list or len(tasks) != len(goal.tasks):
            raise ValueError("resource receipt missing schedule")
        ids, start, end = set(), {}, {}
        for idx, entry in enumerate(tasks):
            task = goal.tasks[idx]
            if type(entry) is not dict or set(entry) != {"id", "start", "end"} or (
                entry["id"] != task.id or entry["id"] in ids
                or type(entry["start"]) is not int or type(entry["end"]) is not int
                or not 0 <= entry["start"] < entry["end"] <= goal.horizon_hours
                or entry["end"] - entry["start"] != task.hours
            ):
                raise ValueError("resource receipt invalid interval")
            ids.add(task.id)
            start[task.id], end[task.id] = entry["start"], entry["end"]
        for task in goal.tasks:
            if any(end[parent] > start[task.id] for parent in task.requires):
                raise ValueError("resource receipt predecessor violation")
        for resource, capacity in goal.capacities:
            for hour in range(goal.horizon_hours):
                pressure = sum(
                    dict(task.resources).get(resource, 0)
                    for task in goal.tasks if start[task.id] <= hour < end[task.id]
                )
                if pressure > capacity:
                    raise ValueError("resource receipt exceeds capacity")
        makespan = max(end.values())
        if type(report["makespan"]) is not int or report["makespan"] != makespan or (
            type(report["slack_hours"]) is not int
            or report["slack_hours"] != goal.horizon_hours - makespan
            or makespan < _bound(goal)
        ):
            raise ValueError("resource receipt wrong deadline or duration")
        if _exists(goal, makespan - 1):
            raise ValueError("resource receipt claims nonoptimal schedule")
        diagnostic = {"type": "NONE", "action_required": False}
    else:
        raise ValueError("resource receipt invalid status")
    return [
        "exact_input_contract", "critical_path_lower_bound", "capacity_per_slot",
        "dependency_order", "global_optimality_proof", "status"
    ], diagnostic
