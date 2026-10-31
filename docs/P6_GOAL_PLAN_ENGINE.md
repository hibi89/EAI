# P6 — CPU-owned goal planning, execution selection and fallback

Updated: 2026-10-31 KST. Source milestone: d203eeeb8b7c6de4acc5a64fdf12043962df3326.

## What this actually solves

**solve-csv** takes an explicit goal (audit two CSVs by a key and 1–8 numeric fields) and EAI independently compiles a bounded sequence of fixed, trusted CPU skills. It does not send evidence to Qwen, train model weights, ask an LLM to decide truth, generate scripts, modify CSVs, or infer causal truth. This is an **initial, one-domain goal planner**, not generalized reasoning or autonomous AGI.

## Alternatives compared

A. Dynamic general-purpose DAG/LLM-generated Python per request: flexible but requires code sandboxing, more elaborate permissions, prompt-injection defense, untrusted execution controls and more regression work. Rejected for early daily use.

**B. Whitelisted typed goal templates (selected):** validated AuditGoal → CPU RuleGoalPlanner → fixed local skill IDs → CPUPlanExecutor → evidence-hash postcondition → structured trace. Predictable costs, no GPU, lower integration risk, simpler tests. Limitation: only predefined goals and limited conditional routes; an escalation can re-scan a CSV.

## Executed flow

~~~text
User CLI goal → validated AuditGoal (read-only)
  → RuleGoalPlanner.compile
  → anchor_sources [csv.sha256.v1]
  → primary selection
       1 metric: csv.reconcile.v1 (P4)
       2–8 metrics: csv.diagnose.v1 (P5)
  → conditional route
       1 metric + CONFLICT: csv.diagnose.v1 escalation
       UNAVAILABLE: csv.schema_inspect.v1 metadata fallback
  → evidence.verify_receipt.v1 (source SHA256 checked again)
  → EAI-owned deterministic response + optional JSON receipt
~~~

Up to five predeclared steps, normally three actually executed, four on escalation/fallback. No arbitrary tool names or generated scripts are accepted. The trace contains step names, skill IDs and statuses plus source evidence.

## Usage

~~~powershell
python -m eai solve-csv examples/sample_sales.csv examples/sample_sales_source_b.csv --key year --values sales --json
python -m eai solve-csv examples/sample_sales.csv examples/sample_sales_multi_drift.csv --key year --values sales orders --json
python -m eai solve-csv examples/sample_sales.csv examples/sample_sales_source_b.csv --key year --values missing_column
~~~

Exit codes: 0 = AGREE, 2 = CONFLICT, 3 = UNAVAILABLE, 1 = invalid input, missing source, time-budget error or failed evidence guard.

## Safety and accuracy

- Two explicitly specified local CSV paths only; same resolved path refused. P4/P5 limits: <=5MiB, <=20K rows, <=32 columns, <=4096 chars per cell; up to 8 distinct metric names; no model/GPU/network requirement.
- Original files remain read-only. Input hashes are anchored before planning and verified after execution. SHA256 is drift evidence, **not** an atomic snapshot, authenticated signature or proof of origin.
- Single-metric AGREE without any matched numeric rows becomes UNAVAILABLE; byte-identical sources are not treated as independent evidence.
- Conflict and unavailable states are never upgraded by a diagnostic fallback. EAI never decides which original is correct or the cause of mismatch.
- Only fixed CPU local-read skills are present; no arbitrary code, shell or privileged operations, no model-written answer, no upload and no SQLite persistence for audit source contents.
- Trace can reveal key values, source names and column schema. Do not publish reports containing private keys.
- --max-seconds (1–120, default 60) checks elapsed time **before stages**; it is NOT a hard mid-scan cancellation mechanism.
- This planner uses deterministic rules, not learned strategies or independent general-purpose language generation.

## Evidence

Linux Python 3.13.5 source mirror: compileall PASS, **146 unittest PASS / 0 FAIL / 0 SKIP**, preserving previous P0–P5 122 tests and adding 24 P6 tests. Local CLI conflict escalation and multi-metric route verified, CSV content unchanged. New GitHub source files (plan_engine.py, __main__.py, test_plan_engine.py) match tested local git-blob SHA exactly. Full byte-identical GitHub checkout test still UNVERIFIED because six unchanged historical local files differ in bytes from the current remote tree.

GitHub Actions source run 41207577469: FAILURE, no job steps and blank runner name; code was not shown running on CI. Owner Windows Python 3.11, real Qwen/Ollama, real SearXNG and CPU/GPU performance tests remain UNVERIFIED. No Production/Vercel target exists (N/A).

## Next gate

Verify exact remote source and owner PC when accessible; diagnose Actions infrastructure from actionable logs. Extend the same typed plan-and-receipt contract to a second useful non-CSV problem domain with read-only effects. Write-capable actions require new explicit approval and safeguards; avoid UI work until core engine reliability is demonstrated.
