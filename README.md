# EAI — Elice Artificial Intelligence

**Current development: P6 independent CPU-owned goal planner** (2026-10-31 KST). Private local-first project, Python >=3.11, standard library only for core tasks, SQLite for local conversation/notes. Qwen/Ollama, when explicitly enabled, is **only an INPUT interpreter**, not the reasoning/verification/answer-authoring engine. GPT-class general intelligence remains a long-term, unproven research goal.

## Run today

~~~powershell
python -m eai health
python -m eai ask "계산 0.1+0.2"
python -m eai ask "비교 A=100,B=120,C=114"
python -m eai ask "기억해: EAI는 CPU 중심"
python -m eai ask "기억검색 EAI"
python -m eai analyze-csv examples/sample_sales.csv
python -m eai verify-csv examples/sample_sales.csv --column sales --metric sum --expected 352
python -m eai reconcile-csv examples/sample_sales.csv examples/sample_sales_source_b.csv --key year --value sales
python -m eai diagnose-csv examples/sample_sales.csv examples/sample_sales_multi_drift.csv --key year --values sales orders
python -m eai solve-csv examples/sample_sales.csv examples/sample_sales_multi_drift.csv --key year --values sales orders --json
python -m eai chat
~~~

### P6 goal planning

The new **solve-csv** command chooses a fixed CPU skill path. It anchors input hashes, selects single-metric reconciliation or multi-metric diagnosis, conditionally escalates conflicts or inspects missing columns, verifies hash continuity, and reports a structured plan receipt. No Python scripts are generated on the fly, no source CSVs are modified, and no network or GPU is required.

The example synthetic data deliberately disagrees at individual keys; CONFLICT (exit 2) is expected. Codes: 0 = AGREE, 1 = invalid/error, 2 = CONFLICT, 3 = UNAVAILABLE. The result proves only internal consistency between those two CSVs, not real-world authenticity.

### P0–P5 preserved

P0 exact arithmetic, optional Qwen intent parser and permission-gated local SearXNG search; P1 SQLite user notes and migration snapshot; P2 numerical comparison and bounded read-only CSV profile; P3 one-file typed claim verification; P4 two-source keyed reconciliation; P5 multi-metric discrepancy candidates. Original HAE/LA/other repositories are not touched.

Optional Qwen requires a locally installed model and local Ollama; optional online retrieval requires explicit --online and a user-configured local SearXNG service which **may forward queries externally**. Neither is automatically installed. No paid API dependency.

### Verification

Local Linux Python 3.13.5: compileall PASS; **146 offline tests PASS / 0 FAIL** with 24 new P6 cases; verified isolated local CLI routes and no source-file writes. The three new/modified P6 source Git Blob SHAs match the tested local source exactly. A full byte-identical remote checkout and Windows 10 Python 3.11/real Qwen/SearXNG are UNVERIFIED. GitHub Actions source run 41207577469 FAILED before visible job steps (runner name blank). No production deployment or Vercel URL applies.

[Status](STATUS.md) · [10-point handoff](HANDOFF.md) · [P6 planner contract](docs/P6_GOAL_PLAN_ENGINE.md) · [P5 diagnosis](docs/P5_MULTI_METRIC_DIAGNOSIS.md) · [ADR-0002 cognitive ownership](docs/ADR-0002_EAI_COGNITIVE_OWNERSHIP.md) · [ADR-0003 CPU/GPU research](docs/ADR-0003_ADAPTIVE_CPU_GPU_RESEARCH.md).
