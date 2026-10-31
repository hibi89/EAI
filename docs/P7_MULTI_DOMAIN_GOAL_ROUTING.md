# P7 — Two-domain typed goal routing

Date: 2026-10-31 KST. Source SHA: 63eabb69dac8ff498126eef85bfcc1f1b7368b2b.

## Purpose
EAI CPU dispatches strictly validated local goal JSON to one of two fixed read-only solvers: choose_options or csv_audit. Optional Qwen is input classification only; no model makes scoring, verification or final decisions.

## Alternatives and decision
A: LLM-generated code and workflows are flexible but require extensive sandbox, provenance and permission protection. Rejected.
B: Whitelisted typed goals and fixed skills are CPU-efficient, deterministic and easier to validate, with limited generality. Selected.

## Contract
Goal JSON <=64 KiB, version=1, no duplicate/extra keys, input SHA256 checked before/after.
choose_options: 1–8 criteria, 2–24 options; explicit decimal-string metrics, directions, weights, scoring bounds and optional hard constraints. Weighted scoring and raw-value Pareto nondominance; incomplete choices not invented.
csv_audit: two explicitly selected local CSV paths, key, 1–8 value fields; reuse of P6 read-only audit planner and hash guard.
Statuses: DECIDED/TIE/UNAVAILABLE for choice; AGREE/CONFLICT/UNAVAILABLE for CSV. CLI exits 0, 2 CONFLICT, 3 UNAVAILABLE, 1 input/runtime error.

## Commands
~~~powershell
python -m eai solve-goal examples/sample_hardware_decision.json --json
python -m eai solve-goal examples/sample_csv_audit_goal.json --json
~~~

## Evidence and unknowns
P7 local Linux Python 3.13.5 mirror: 180 tests PASS / 0 FAIL including 34 P7. All seven P7 changed files' Git blobs matched local tested source. Entire byte-identical GitHub checkout, real Windows Python 3.11 and remote CI PASS unverified. GitHub Actions returned pre-step FAILURE with no actionable runner traces. No cloud service, write tool, paid API or HAE/LA change.
P8 further verifies result receipts; see P8_VERIFIED_GOAL_RECEIPTS.md.
