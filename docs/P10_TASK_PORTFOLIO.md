# P10 — exact bounded local task portfolio (2026-11-09)

## Alternatives evaluated

- Greedy highest-value first: O(n log n), minimal CPU but may miss the optimal combination when dependencies and two budgets interact.
- Exact subset enumeration: 12 tasks at most, 4095 nonempty subsets, deterministic CPU-only and transparent. Selected because it correctly finds the maximum user-provided value within hours, costs, and dependencies. Independent verification enumerates itertools.combinations instead of copying solver bitmasks.

## Contract

Goal v1 kind `plan_tasks`, `goal`, `max_hours`, `max_cost`, and `tasks` with `id`, `hours`, `cost`, `value`, `requires`. All numeric quantities are finite fixed-point decimal strings; negative or float inputs and unexpected keys denied. 1–12 tasks, 64KiB goal limit, dependencies must exist and be acyclic. Positive-value optimal selection returns DECIDED; equal maxima return TIE without an arbitrary selected winner; no positive feasible subset returns UNAVAILABLE. Strictly read-only, no external model, no spend, no task execution. Output includes exact resource totals, maximum value, first eight sorted optimal candidates and complete tie count. User-provided utilities and effort estimates are not verified real-world facts.

CLI: `python -m eai solve-goal examples/sample_task_portfolio_goal.json --json`.
Tests: `python -m unittest discover -s tests -v` and `python -m compileall -q eai tests`.
Windows 10/11 local testing, real Qwen/Ollama, model generalization, customer data and commercial distribution are separate unverified gates.

## Current executable evidence — 2026-11-10 KST
- Feature+test SHA `843a1426ac4c2dcb4c0e957768bc94ea04078f02` [GitHub Actions #42664669185](https://github.com/hibi89/EAI/actions/runs/42664669185) **completed/success**, Python 3.11 Linux, exact-source 229 unittest PASS (18 new P10), 0 FAIL, compileall & CLI health smoke PASS.
- Budget, dependencies, tie/hold, Decimal, forged receipts, read-only local files and CLI have regression tests; source/Windows/customer deployment independent acceptance remains open.
- Final full product 35→36% is a provisional management estimate reflecting the **new task planning domain**, not CI pass percentage or GPT-level capability.
