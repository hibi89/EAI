# P2 — EAI independent numeric comparison and local CSV profile

Date: 2026-10-31 KST. Status: implemented source and local CPU tests; not a general-purpose AI or production deployment.

## Owner benefit
Useful work without installing Ollama/Qwen or a GPU: compare numeric KPIs and inspect a local CSV using deterministic CPU algorithms. This is an incremental part of the EAI cognitive toolchain, not proof of GPT-level intelligence.

## Alternatives
A. Feed whole CSV and comparisons into Qwen. Fast to prototype but conflicts with ADR-0002 (model may generate unverified conclusions), consumes model compute/VRAM, risks disclosure and creates nondeterministic output. Rejected.
B. Explicit typed comparison syntax and separate user-invoked read-only CSV analyser with Python standard library Decimal/csv. Deterministic, testable, no GPU/cloud dependencies, simple to maintain. Selected. Cost: limited language flexibility and bounded basic aggregates.

## Flow and examples
```text
python -m eai ask "비교 A=100,B=120,C=114"
python -m eai analyze-csv examples/sample_sales.csv
python -m eai analyze-csv "C:\\data\\sales.csv" --encoding cp949
```
EAI own intent rules -> Compare solver -> ResultSpec -> EAI fixed renderer. Explicit syntax bypasses Qwen even when installed. User-selected CSV path -> size check -> streaming UTF-8/CP949 csv reader -> row/count/types -> decimal aggregates -> CLI output. No automatic file reading or persistence of CSV contents. No LA/HAE edits or model training.

## Correctness and limits
- Comparison: 2–16 unique named decimal observations, max 500 chars, max 24 integer and 12 fractional digits per value, rank stable on ties, 90-digit Decimal work precision, percentage rounded to 2 decimals. Only consecutive **input-order** changes are shown; EAI does not infer chronological order or units. Previous value <=0 disables growth percentage.
- CSV: an **explicit** local path; <=5 MiB; <=20,000 data rows; <=32 columns; <=4,096 characters per field; unique headers <=60 chars. Expects UTF-8-sig by default; CP949 manual option. No arbitrary code, formulas, network, shell, or original-file writes. Numeric columns aggregate min/max/sum/mean (mean six decimal places); mixed/text columns do not produce numeric statistics. Empty CSV/header mismatch/invalid encoding/oversized data fail closed.
- Current CSV command prints only column names and aggregate data; does not print raw rows. Column headers might themselves contain sensitive information, so users should not share terminal output publicly without reviewing it.
- This is not forecasting, inference, regression, chart generation, RAG or original model training. Verification covers arithmetic and schema, not the truth of user data.

## Reproducible validation
```text
python -m compileall -q eai tests
python -m unittest discover -s tests -v
python -m eai ask "비교 2023=100,2024=125,2025=110"
python -m eai analyze-csv examples/sample_sales.csv
```
Local Linux Python 3.13: 55/55 PASS incl. existing P0/P1 regression, model bypass, no network, invalid input, large decimal exactness, zero baseline, read-only CSV, UTF-8/CP949, file/row/field bounds, CLI subprocess. The modified source Git blob SHAs matched GitHub on readback. Existing `storage.py` and `tests/test_memory.py` differ in formatting between the local test directory and GitHub P1, so a byte-identical entire repository test is **not** claimed. Windows Python 3.11/real Qwen/real SearXNG/GitHub Actions success are NOT VERIFIED.

## Next acceptance
Local Windows 10 Python 3.11 smoke, optional real Qwen intent parser, real search consent, full exact-checkout test, and one actual user CSV sample read-only with user permission. Larger CSV, chunked aggregation and advanced comparison features are future proposals, not completed work.
