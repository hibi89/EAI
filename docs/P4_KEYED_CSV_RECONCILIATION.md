# P4 — Independent CPU keyed cross-source CSV reconciliation

Date: 2026-10-31 KST.
Source commit: `18da5701ae0262607f397b54e873b4b50cfeff2f`.
Owner objective: make EAI itself find concrete contradictions between local data sources without asking Qwen to reason or generate answers.

## Comparison of two implementations
A. Compare only CSV totals (fast, but misses swapped records and row-level contradictions even when totals agree). Rejected as insufficient for actual error investigation.
B. **Keyed, read-only reconciliation (selected)**: use existing bounded P2 CSV parser and P3 hash validation, index only unique keys and one numeric column for each of two explicitly supplied files, compare key unions with exact Decimal arithmetic. More CPU/validation work than totals but finds changed/missing rows. No HAE/LA modifications, network or GPU requirements.

## Example

```powershell
python -m eai reconcile-csv examples/sample_sales.csv examples/sample_sales_source_b.csv --key year --value sales
python -m eai reconcile-csv examples/sample_sales.csv examples/sample_sales_source_b.csv --key year --value sales --json
python -m eai reconcile-csv "C:\data\source_a.csv" "C:\data\source_b.csv" --key ID --value amount --tolerance 0.01 --encoding cp949
```

The bundled synthetic files both total **352** in sales; two keyed values differ. The sample therefore returns `CONFLICT` (exit code 2) and details 2024/2025 values.

## Decision statuses and safety
- `AGREE` (exit 0): all eligible keyed numeric observations match within the supplied absolute tolerance. **This is not verification of independent real-world facts**.
- `CONFLICT` (exit 2): at least one numeric mismatch or a key present in one source but absent in the other; takes precedence over nonnumeric/unavailable fields.
- `UNAVAILABLE` (exit 3): required column missing, some key observations nonnumeric/blank, or two supplied files have byte-identical SHA256 (not demonstrably independent evidence). Zero hidden replacement for missing values.
- Input/IO/validation error (exit 1): invalid tolerance, encoding, duplicate/blank/overlong key, malformed or oversized CSV, same resolved path.
- CLI emits bounded JSON or text, counts and at most **20** representative discrepancies (additional count included); source reports basename, content SHA256, rows and columns. Key strings may be sensitive: terminal output is LOCAL; do not share it publicly without review.

## Bounded requirements
Two explicitly named CSV paths, each <=5 MiB, <=20,000 rows, <=32 columns, <=4,096 chars per field. One unique key (<=120 chars/record), one bounded numeric column, exact fixed-point decimals (24 digits integer + 12 fractional max). CP949 or UTF-8 selected explicitly. File hash before/after read detects content drift; no cryptographic source signature and no atomic filesystem snapshot guarantee. CSV files are never modified, stored in SQLite, uploaded or sent to a local LLM. Key comparison is exact and case-sensitive, no inferred units, dates, join normalization, scaling or row-by-row document authenticity.

## Executed tests and limits
```powershell
python -m compileall -q eai tests
python -m unittest discover -s tests -v
python -m eai reconcile-csv examples/sample_sales.csv examples/sample_sales_source_b.csv --key year --value sales --json
```

Local Linux Python 3.13.5: **97/97 PASS**, including 23 new P4 tests and 74 prior P0-P3 tests. Tests cover equal-but-reordered rows, same-sum swapped values, absolute tolerance, missing/invalid data, duplicates, oversize inputs, CP949, no network/model calls, bounded details and CLI exit 0/1/2/3. New/modified P4 source file Blob SHAs exactly matched readback from GitHub. Earlier P3 ZIP has five older code/test blobs whose bytes differ from GitHub, so a **complete byte-identical remote checkout PASS is not claimed**.
Latest P4 GitHub Actions run `41204686535`: FAILURE after ~2 seconds, runner_name empty, job steps []. Cause unverified; no claim that tests ran there. Actual Windows 10/Python 3.11, real Qwen and SearXNG, GPU profiling: UNVERIFIED. No production/Vercel endpoint.

## Next
P5 only after actual usage: compare multiple metrics and file provenance, possibly hierarchical grouped matching, without losing bounded deterministic proof. Preserve the original files, use a full byte-identical checkout for independent regression, and resolve CI runner/account issue through actionable logs or owner-approved settings inspection.
