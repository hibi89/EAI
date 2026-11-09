# EAI P21 — deterministic resource-constrained schedule (2026-11-10 KST)

Tenth typed CPU problem solver: exact, bounded scheduling of dependent tasks that share human/device capacities. Does **not** execute tasks, book resources, assign real staff or update calendars.

## Alternatives

- A. Fast greedy first-available schedule. Cheap and simple, but may be far from the shortest schedule and incorrectly claim optimal execution.
- B. Enumerate possible integer-hour task starts using strict constraints and a finite search-state budget, choose the lowest feasible makespan; independently verify every capacity/dependency slot and disprove any claimed shorter finish with a second interval-overlap search. **Selected** for transparent small-task optimality, with explicit failure rather than approximate claims when budget exceeds bound.

## Goal contract

```json
{
  "version": 1, "kind": "resource_schedule",
  "goal": "Plan release verification", "horizon_hours": 8,
  "capacities": {"cpu": 1, "qa": 1},
  "tasks": [
    {"id": "ingest", "hours": 2, "requires": [], "resources": {"cpu": 1}},
    {"id": "prepare", "hours": 2, "requires": [], "resources": {"cpu": 1}},
    {"id": "verify", "hours": 1, "requires": ["ingest","prepare"], "resources": {"qa": 1}}
  ]
}
```

Run `python -m eai solve-goal examples/sample_resource_schedule_goal.json --json`. The synthetic case requires serial CPU for ingest/prepare (4 hours) then QA verify (1 hour); expected shortest makespan **5 hours**. It is one toy discrete-time task problem, not a generalized project schedule.

- 2–7 tasks, each 1–8 integer hours with <=6 predecessors and resource demands. 1–3 explicitly named capacities (1–4 units), required resource units 1–capacity. Horizon 1–24 integer hours. Strict IDs and topological ordering, no cycles, duplicate keys or extra action fields.
- Earliest finish critical-path and total resource-workload lower bounds; exhaustive search from lower bound to horizon, fail closed after 100,000 explored states. For each solution, `DECIDED` means a feasible globally minimum makespan within this discrete bounded contract. `UNAVAILABLE` means no feasible plan within the selected horizon. Error means invalid input or proof budget exceeded — never silently an approximate plan.
- Independent receipt checker reconstructs source rules, slot-by-slot capacity and predecessor compliance and tries to disprove optimality by finding a schedule with a strictly shorter makespan. For `UNAVAILABLE`, it checks no feasible schedule within the horizon. Exact goal JSON hash is included in the router and P12/P14 manifests. Good status may unlock dependent computations but never executes anything.
- No network/API/LLM, background jobs, file writes or privileged operations. Python 3.11 stdlib. Existing P11 critical-path results are preserved. This solver adds the **resource** dimension not previously considered by P11.

## Verification criteria

GitHub exact commit: compileall, full unittest, CLI smoke and dedicated synthetic P21 tests for dependent scheduling, insufficient capacity, forged optimality, cycles, resource overload, CLI exit codes, batch and DAG gating. Windows10/11 native, actual human resource estimates, Qwen/SearXNG and commercial release remain **UNVERIFIED/HOLD**.
