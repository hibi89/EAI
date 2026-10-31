# P8 — Shared result verification and bounded diagnostics

Date: 2026-10-31 KST. Source SHA: e33cdd2c6100c781e01257b311726cfd8a21b11e.

## Purpose
P7 only checked typed routing, a status string and unchanged goal file. P8 verifies result invariants against original source data before marking the receipt verified.

## Two alternatives
A: automatically rerun Qwen or relax user constraints on failure; risks contradicting user intent, untrusted suggestions and uncontrolled cost. Rejected.
B: CPU-only independently recomputed postconditions, deny inconsistent receipts, and provide bounded advisory next checks for valid but unresolved results. Selected.

## Verification rules
Choice route recomputes missing value sets, hard-constraint violations, exact Decimal weighted scores and unrounded ranking, Pareto dominance and winner/status consistency. Missing or contradictory data cannot be promoted into a winner.
CSV route checks P6 plan version, strategy, key/metrics, source filenames and freshly read SHA256, primary/final status, allowlisted skill events, final evidence verification, and conditional escalation or schema fallback.
Receipt version: eai.receipt.guard.v1. Inconsistency raises ValueError (CLI exit 1).
Valid unresolved results return advisory diagnostic types: TIE_REVIEW, NO_FEASIBLE_OPTION, CONFLICT_REVIEW, SOURCE_SCHEMA_REVIEW. Candidate detail capped at 12. No auto-modification of criteria, user files or privileged actions; no network, model or GPU.

## Usage
~~~powershell
python -m eai solve-goal examples/sample_hardware_decision.json --json
python -m eai solve-goal examples/sample_csv_audit_goal.json --json
python -m unittest discover -s tests -q
~~~

## Evidence
Linux local Python 3.13.5: compileall PASS and 201 tests PASS / 0 FAIL / 0 SKIP, including 21 new P8 tests. Tests cover forged winners, scores, Pareto, CSV hashes, unapproved skills, missing steps, source immutability, tie/constraint diagnostics and no network. Three P8 Git blob SHAs exactly match local tested source.
GitHub Actions run 41210358928 FAILURE before visible job steps; root cause unknown. Full byte-identical remote checkout and Windows 3.11 unverified. SHA256 is not a proof of source authenticity; user-provided data quality remains unknown. P6 time budgets are per-stage admission, not hard cancellation.
