# P3 — EAI independent CPU CSV claim verification

Date: 2026-10-31 KST. Source milestone: c108648b0e153b8252e8ff0faf715518a75d4440. This is **narrow, user-source-bound verification**, not a general GPT-level cognition claim.

## Why / scope

For an explicitly named local CSV and one or more user-supplied numeric claims, EAI uses its own deterministic CPU Decimal calculations and returns VERIFIED (consistent with that CSV under stated tolerance), CONFLICT (numeric discrepancy), or UNAVAILABLE (missing column/non-numeric statistic). It reports actual value, absolute delta, the declared tolerance, file SHA256 and source row/column count. It does NOT certify that the CSV itself is authentic, a valid historical record or externally true. Qwen does not write answers or verify claims.

## Alternatives weighed

A. **Reuse existing P2 inspect_csv profiler (selected)**: bounded input limits, single CSV profiling pass for up to 24 claims, clear regression scope, no GPU or new dependencies. Tradeoff: averages are six-decimal-place rounded; source file hashing occurs twice.
B. Specialized new streaming query/verifier: potentially richer predicates/grouping, but duplicates parser/encoding security controls and adds maintenance/validation cost. Defer until real tasks warrant it.

## Use

\`\`\`powershell
python -m eai verify-csv examples/sample_sales.csv --column sales --metric sum --expected 352
python -m eai verify-csv examples/sample_sales.csv --column sales --metric sum --expected 300 --json
python -m eai verify-csv examples/sample_sales.csv --claims examples/sample_sales_claims.json --json
\`\`\`

Claims JSON = array of 1–24 objects, e.g. \`{"column":"sales","metric":"sum","expected":"352","tolerance":"0"}\`. Decimal numbers must be JSON strings. Strict schema, <=32KiB, no extra/duplicate keys, NaN/Infinity/exponent not accepted; tolerance must be nonnegative. Metrics: sum, min, max, avg, missing, numeric_count, text_count. Aggregation of text/mixed columns is UNAVAILABLE, not silently zero.

Exit codes: 0 VERIFIED, 1 input/IO error, 2 CONFLICT, 3 UNAVAILABLE. Overall CONFLICT takes precedence over UNAVAILABLE, then VERIFIED. This contract is suitable for scripted workflows with no generated nodes.

## Safety & accuracy

Source CSV is explicitly specified; read-only and no remote calls; <=5 MiB, 20K rows, 32 columns, 4096 chars/field. Before and after parsing, SHA256 is computed; inconsistent content invalidates a result. SHA256 is not a signature and does not prevent malicious filesystem races. Only file basename/hash/aggregate results appear in response. Actual rows are never posted externally or committed. The existing profiler rounds average to six decimals, and that precision limit is disclosed; values and columns have no inferred units/dates.

## Verification evidence

Local Linux Python 3.13: compileall PASS; 74 unittest PASS / 0 FAIL / 0 SKIP (19 P3 tests). Single claim, batch, mismatch, missing source, unsupported schema, large/malformed JSON, no external Qwen/network call, source mutation, exact hash and distinct CLI exit-code checks PASS. Four P3 source Git Blob SHAs read back from GitHub and matched local Git SHA. This does **not** prove complete byte-identical repository tests. GitHub Actions source-run 41203228592 ended FAILURE before any visible job step (runner_name empty); root cause unknown. Windows 10 Python 3.11 and real Ollama/SearXNG/GPU are unverified.

Next: full exact checkout and owner-PC smoke when accessible; avoid rerunning zero-step CI without actionable logs. Extend verifiers based on real user evidence problems, not speculative broad capability claims.
