## 2026-11-12 — Verified P31–P34: provisional engineering **85%** / RELEASE HOLD

At exact [source SHA `736dcf017aed`](https://github.com/hibi89/EAI/commit/736dcf017aed3144121d6b30c800575dc2599863), [CI #43115273614](https://github.com/hibi89/EAI/actions/runs/43115273614) Linux Python3.11 **623 discovered / 622 PASS / 1 Windows-only SKIP / 0 FAIL**, compiled CLI and real clean-unpacked portable ZIP journeys PASS. Seven-file candidate SHA256 `d2df7b5bc4737f6b0a6262587be2f032f96e3b391272524552c7538592b7443f` ([private Actions artifact #13896909925](https://github.com/hibi89/EAI/actions/runs/43115273614/artifacts/13896909925)); this is **unsigned / not commercial**. Scope weighting 70+5 P31 new relational key engine+independent source receipt +4 P32 source-free owner HTML/JSON integrity +4 P33 offline candidate ZIP/Windows synthetic runner +2 P34 extracted packaged E2E = **85% provisional engineering**. Real customer Windows, genuine Qwen, authorized customer sources/PII, legal/signing/support/buyer launch remain UNVERIFIED and release HOLD.

```powershell
python -m eai solve-goal examples/sample_key_coverage_goal.json --json
python -m eai customer-review --spec examples/sample_key_coverage_goal.json --output-dir ..\\EAI-NEW-REVIEW --ack-authorized-local
python -m eai verify-review --output-dir ..\\EAI-NEW-REVIEW
python scripts/build_customer_candidate.py --output dist/EAI-Offline-Review-0.1.0-beta.zip
```

---

## 2026-11-11 — Latest provisional engineering milestone: **70%**, retail RELEASE HOLD

[GitHub Actions exact P23–P30 feature/test SHA `8cdad74...`](https://github.com/hibi89/EAI/actions/runs/42960081154): Ubuntu Python3.11 `compileall`, **582/582 full unittest PASS**, CLI smoke and real portable-`.pyz` synthetic journey PASS. New P23–P30: source-first CSV Advisor, SHA-pinned CPU/optional **local** Qwen input-only goal selector, independent user SHA approval, private-value-minimized HTML report, deterministic portable Python `.pyz`, direct no-JSON CSV/text analysis, new verified `csv_distribution_shift` (12 bounded goal kinds), packaged E2E. Actual Qwen model, Windows/user data/customer installation and commercial release are **NOT VERIFIED**. [Milestone, exact scope and blockers](docs/P23_P30_MILESTONE_70_20261111.md).

```powershell
python -m eai advise-csv --root examples --source sample_relationships.csv --json
python -m eai quick-goal --kind csv_relationships --root examples --source sample_relationships.csv --columns ads sales refunds --json
python -m eai solve-goal examples/sample_csv_relationships_goal.json --json
python -m eai export-report examples/sample_csv_relationships_goal.json --format html
python scripts/build_portable.py --output eai-local.pyz
python eai-local.pyz --version
python -m unittest discover -s tests -q
```

`build_portable.py` refuses to overwrite an existing `.pyz`, contains only EAI Python source, does not bundle Python runtime or a model. `export-report` prints HTML only: user redirecting to a new file is explicit. `select-goal` alone never runs a task; `run-approved` requires independent owner ID plus both SHA256 strings. These are local CPU-only read-only workflows. Any customer data, paid usage, remote transmission or publication requires authorization.

---

## Latest source-verified milestone — P20/P21/P22, 2026-11-10 KST

**Provisional whole-product completion: 50% / 100%; retail RELEASE HOLD.** Three new independent CPU skills:

- `local_evidence_search`: explicit TXT/MD exact-token line matching with SHA256 source provenance, no snippets by default.
- `resource_schedule`: bounded exact minimum-duration schedule with shared resource capacity + predecessors, independent capacity/optimality verification.
- `csv_robust_outliers`: local CSV median/MAD anomalies, complete-case input quality, independent raw-data proof; not an ML or fraud verdict.

```powershell
python -m eai solve-goal examples/sample_local_evidence_goal.json --json
python -m eai solve-goal examples/sample_resource_schedule_goal.json --json
python -m eai solve-goal examples/sample_robust_outliers_goal.json --json
python -m eai doctor --json
python -m unittest discover -s tests -q
```

The first two synthetic goals expect `AGREE`/`DECIDED` (exit 0); P22 deliberately flags an outlier (CONFLICT/exit 2). Linux Python3.11 GitHub full regression **475/475 PASS**, compileall + CLI smoke PASS at code/test SHA `88af3412d59dad8ea848322bdb75292adb7db9e4` [Actions #42696296697](https://github.com/hibi89/EAI/actions/runs/42696296697). Historical tests 437 (P20) and 456 (P21) also passed at their exact SHAs. Demo goals above are documented but CI smoke step only directly calls version/health; tests exercise temporary synthetic scenarios through CLI. Current 11 bounded goal kinds, P13 doctor 10 probes. Real owner Windows, Ollama/Qwen/SearXNG, customer files and retail release **not verified**. Past 45% notes below are historical.

---

## Latest verified feature — P19 CPU relationships (2026-11-10 KST)

**Estimated whole-product completion: 45% / 100%; retail RELEASE HOLD.** P19 adds the eighth independent typed CPU goal `csv_relationships`: bounded local 2-6 numeric CSV columns, complete-case Pearson associations and a separate independent source-backed evidence guard, with SHA256. Sample:

```powershell
python -m eai solve-goal examples/sample_csv_relationships_goal.json --json
python -m eai doctor --json
python -m unittest discover -s tests -q
```

The synthetic example is expected to report AGREE (exit 0), +1 and -1 correlations; see [P19 contract](docs/P19_CPU_RELATIONSHIP_DISCOVERY.md). Real customer data, row values and other sources are not uploaded. Exact feature/test SHA `d376a4dda5595385bd6a2f189b5e20e6090e4b27` [CI 42691179558](https://github.com/hibi89/EAI/actions/runs/42691179558) Linux Python3.11 **417/417 PASS / 0 FAIL, syntax and CLI smoke PASS** (+22 P19 tests); earlier failed P19 CI was corrected by test expectations only. Offline doctor still has 10 existing checks. Windows native, live Qwen/Ollama, SearXNG, commercial validation/packaging/production remain unverified.

---

## Current P18 exact-source verification — 2026-11-10 KST

**Provisional whole-product completion: 44% (RELEASE HOLD).** P18 adds the seventh independently verified CPU goal `sqlite_table_audit`: owner-selected local SQLite table, missing required values and duplicate keys, SHA-256 + independent guarded receipt. Never runs owner-provided SQL or emits row values. P12 batch/P14 DAG review-gating is supported.

Create a local goal JSON beside the SQLite file (no customer DB is included in GitHub):

```json
{"version":1,"kind":"sqlite_table_audit","goal":"Inspect invoices","source":"invoices.sqlite3","table":"invoices","required":["id","amount"],"unique_by":["id"]}
```

Then run `python -m eai solve-goal path/to/goal.json --json`. Exit 0/2/3 means AGREE/CONFLICT/UNAVAILABLE; invalid source or contract returns 1. See [P18 contract](docs/P18_SQLITE_TABLE_AUDIT.md). Synthetic exact-source commit `ef220a017c3f7a14d20aaadfdbcdb40bd3feec28` passed [GitHub Actions 42688535530](https://github.com/hibi89/EAI/actions/runs/42688535530): **395/395 PASS, syntax/CLI smoke PASS** on Linux Python3.11 (+20 P18 tests). P13 doctor remains 10 fixture checks. Actual user Windows/Qwen/SearXNG/customer database/product packaging/paid release **not verified**. All 43% P16/P17 notes below are historical snapshots.

---

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
