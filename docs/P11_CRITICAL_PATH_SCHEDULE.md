# EAI P11 — independent critical-path schedule analysis

Updated: 2026-11-10 KST

## Design choice
- **Sequential sort**: low cost and simple, but cannot compute parallel critical-path duration, late-start slack or accurate schedule feasibility with explicit dependencies.
- **Typed directed acyclic graph CPM**: bounded topological forward/backward passes with Decimal exact arithmetic and an independent recursive verifier. Chosen. Time cost O(V+E), no external APIs, no autonomous edits, no added dependencies. Read-only.

## Strict v1 contract
A single JSON file <=64KiB with version 1, kind `schedule_tasks`, goal, `deadline_hours` string and 1-24 tasks, each with id, `hours` decimal string and explicit `requires` task ID list. Missing/self/cyclic requirements, duplicate IDs, negative/float durations, unknown fields and injection keys are rejected.

The forward pass computes earliest starts/finishes; backward pass computes latest starts/finishes and total float using the **minimal computed project makespan as the reference**, not the user deadline. Output includes all tasks, representative lexicographically first critical path, **all zero-slack critical tasks**, earliest ready tasks, deadline margin and DECIDED if within the deadline or UNAVAILABLE if exceeded. It does **not** adjust user constraints or execute/schedule real work. When multiple critical paths exist, only one representative path is shown; the critical-task set preserves parallel critical branches.

Parallel capacity is unlimited in this mathematical CPM model. There is **no** worker allocation, calendar/timezone, working-hours model, stochastic duration or real date-time promise. Estimates are user inputs, not verified actuals.

## Independent verification
The EAI receipt guard separately computes longest predecessor and successor distances via recursive memoization, checks each reported time, all slack/critical flags, representative path, deadline, ready tasks, schema and constant safety scope. Mismatches are rejected before PASS. Tests include chain, parallel, ties, zero duration, exact decimals, deadline miss, graph validation, forgery and CLI read-only behavior.

## Usage
`python -m eai solve-goal examples/sample_task_schedule_goal.json --json`
`python -m unittest discover -s tests -v`

## Remaining gates
GitHub-exact Python 3.11 CI, real Windows 10/11 CLI, owner-provided workload calibration, Qwen/Ollama intent-only integration, product packaging and launch rights are separate gates. Do not count feature tests as Windows/customer acceptance.

## Verified acceptance — 2026-11-10 KST

- Source and tests SHA: `42d6b53400fd841d6f5f4e3db0e97583bf3996cd`. [GitHub Actions #42666810963](https://github.com/hibi89/EAI/actions/runs/42666810963) completed/success, Python 3.11, exact-source compileall and 249/249 unittest PASS, CLI health smoke PASS. Includes 18 P11 tests and a later critical fixed-point precision regression.
- Earlier P11 first SHA `7e625cd356cc579634ca0b8842cb2e1e9893f8d3` passed 247/247 tests but predated the Decimal high-precision hardening. It is historic, not the final verified source.
- The P10 resource solver and guard also use a shared 90-digit evaluation context, validated by a 24-integer/12-fraction digit extreme input regression test.
- Owner Windows/local model, customer scheduling, actual workforce/timezone constraints and commercial release remain UNVERIFIED. This is an explanatory, bounded mathematical schedule and not a real-world task executor.
