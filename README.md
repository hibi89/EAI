# EAI — Elice Artificial Intelligence

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
