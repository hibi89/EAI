# EAI — Elice Artificial Intelligence

## Latest exact-source verification — 2026-11-10 KST

**Estimated whole-product completion: 43% / 100% (retail RELEASE HOLD).** New P16/P17 independent typed CPU skills: CSV quality rule audit and two-file schema drift detection. Both read only local CSV, bound each to <=5MiB / <=20,000 data records, preserve original SHA256 and use a separate independent receipt re-evaluation.

```powershell
python -m eai solve-goal examples/sample_csv_quality_goal.json --json
python -m eai solve-goal examples/sample_csv_schema_drift_goal.json --json
python -m eai doctor --json
python -m unittest discover -s tests -v
```

The two synthetic sample goals deliberately return `CONFLICT` (CLI exit code 2), which does **not** mean the CLI broke; it proves the rules detected supplied data discrepancies. Doctor now performs 10 synthetic checks. Linux Python3.11 exact feature+test SHA `9b0b7438cd0e8756e87c7ca4d03d23a731773d91`: [Actions 42680542935](https://github.com/hibi89/EAI/actions/runs/42680542935) **375/375 PASS, 0 FAIL, syntax and CLI smoke PASS**. Real Windows, customer datasets, installed Ollama/Qwen/SearXNG, general AI and commercial launch still unverified. This is not an AI general intelligence claim.

Earlier 41%/320-pass and 42%/348-pass descriptions below are historical snapshots.

---


## Latest source-verified acceptance — 2026-11-10 KST

**Whole product completion provisional: 41% / 100%.** P15 adds **read-only manifest generator** to make P12/P14 usable without manually calculating SHA256:

```powershell
python -m eai make-manifest --mode batch --root examples --goal choose=sample_batch_choice.json --goal schedule=sample_batch_schedule.json
python -m eai make-manifest --mode pipeline --root examples --goal choose=sample_batch_choice.json --goal schedule=sample_batch_schedule.json --requires schedule=choose
```

Output is JSON on stdout only; user-initiated redirection to a file is required before running `batch-goals` or `pipeline-goals`. The builder does not execute goals or modify files.

Source+tests SHA `c35269299f0cdfaa42c51eb8351db50b9e7ec93d` [GitHub Actions #42676269100](https://github.com/hibi89/EAI/actions/runs/42676269100) Linux Python3.11 **320/320 PASS, compileall/CLI smoke PASS**, including 19 P15 new tests and 301 prior regressions. Native Windows, live Qwen/Ollama, customer data, actual production and distribution are NOT verified; retail release HOLD.

Historical preceding 40% and 301-test notes below remain dated records and must not be read as the latest status.

---


## Current verified development status — 2026-11-10 KST

**Provisional whole-product completion: 40% / 100%.** P0–P14 typed CPU-local engine has four goal types (choice, CSV audit, task portfolio, dependency CPM), SHA256-pinned batch and dependency pipeline, and an 8-check offline doctor. Optional Qwen/Ollama parses INPUT only; there is no GPT-class general agent. Feature+tests SHA `bbd01576eed2573ffeab5a70eec0662fcb40bad0` [GitHub Actions #42675220982](https://github.com/hibi89/EAI/actions/runs/42675220982) **Python3.11 Linux 301 PASS / 0 FAIL; compileall & CLI smoke PASS**.

```powershell
python -m eai doctor --json
python -m eai solve-goal examples/sample_task_portfolio_goal.json --json
python -m eai solve-goal examples/sample_task_schedule_goal.json --json
python -m eai batch-goals examples/sample_goal_batch.json --json
python -m eai pipeline-goals examples/sample_goal_pipeline.json --json
python -m unittest discover -s tests -q
```

Windows double-click offline diagnostic: `RUN_EAI_DOCTOR.cmd`. The software cannot claim Windows native, real Ollama/Qwen, live SearXNG, actual customer data, paid distribution or general AI verification based only on this Linux CI. **Retail release HOLD.**

Historical P0–P8 README below is a dated archive; its original statements about 201 tests and Actions failure were correct only at the time, not the present status.

---


Private, local-first, CPU-first personal EAI. Qwen is optional INPUT classification only. EAI-owned deterministic solvers perform execution, scoring, evidence checks and response rendering. Broad GPT-level reasoning remains a long-term research target, not a completed capability.

## Quick start — Python 3.11+
~~~powershell
python -m eai health
python -m eai ask "계산 0.1+0.2"
python -m eai ask "기억해: EAI 테스트"
python -m eai ask "기억검색 EAI"
python -m eai analyze-csv examples/sample_sales.csv
python -m eai verify-csv examples/sample_sales.csv --column sales --metric sum --expected 352
python -m eai solve-csv examples/sample_sales.csv examples/sample_sales_source_b.csv --key year --values sales --json
python -m eai solve-goal examples/sample_hardware_decision.json --json
python -m eai solve-goal examples/sample_csv_audit_goal.json --json
python -m unittest discover -s tests -q
~~~

P7 supports two typed JSON goals: choose_options (hard constraints, weighted scoring and Pareto validation) and csv_audit (existing read-only P6 plan). P8 verifies the resulting receipt against original goals or source CSV hashes and permitted skills. It fails closed on false winners, tampered scores/hashes, missing provenance and unsupported execution traces. Valid ties/unknowns get bounded advisory hints, never silent criteria relaxation.

Actual local test mirror: Linux Python 3.13.5, 201 PASS / 0 FAIL through P8. The three P8 modified/new Git blobs match local tested code. Whole exact GitHub checkout, actual user Windows Python 3.11, Ollama/Qwen, SearXNG, GPU tuning and GitHub Actions success remain UNVERIFIED. GitHub Actions fails before visible job steps; cause unknown. No Vercel/Production deployment applies.

Default operations require neither GPU, paid API nor cloud services. Online lookup requires explicit --online with a separately configured SearXNG localhost server; that service may send queries externally. No HAE/LA/main modification.

Docs: STATUS.md, HANDOFF.md, docs/P7_MULTI_DOMAIN_GOAL_ROUTING.md, docs/P8_VERIFIED_GOAL_RECEIPTS.md, docs/ADR-0002_EAI_COGNITIVE_OWNERSHIP.md, docs/ADR-0003_ADAPTIVE_CPU_GPU_RESEARCH.md.
