# P19 — CPU-owned numeric relationship discovery (2026-11-10 KST)

Eighth typed goal: `csv_relationships`. This is a **local statistical relationship audit**, not causal inference, prediction or a claim of general-purpose intelligence.

## Alternatives

- A: permit arbitrary user Python expressions or SQL and statistics libraries. Flexible but unbounded execution, dependency and unauthorized data access risks.
- B: strict versioned CSV goal with 2–6 explicitly named numeric columns, bounded complete-case Pearson correlations, six-decimal coefficients and a separate two-pass raw-moment verification. **Selected** because it is predictable, offline, easy to audit and makes a new analytical decision available independently of Qwen.

## Contract and example

```json
{"version":1,"kind":"csv_relationships","goal":"Investigate linked metrics","source":"metrics.csv","encoding":"utf-8-sig","columns":["ads","sales","refunds"],"min_rows":5}
```

Run `python -m eai solve-goal examples/sample_csv_relationships_goal.json --json`. The synthetic sample intentionally has `ads` vs `sales` Pearson +1, and `ads` vs `refunds` -1. Column names and aggregate results are displayed; **raw row/cell/key values are not**. No source file or local database is modified.

- Files within goal directory only (no parent paths, absolute paths, drive names or symlink escapes); each CSV <=5MiB, <=20,000 records, <=32 columns, <=4096 characters per cell.
- Select 2–6 distinct valid existing headers and integer `min_rows` 5–20,000. Input accepted only as finite fixed-point decimal strings (up to 24 integral and 12 decimal digits, using strict `_NUMBER` grammar) with `utf-8`, `utf-8-sig` or `cp949`.
- Exactly one row is considered complete if **every** selected numeric column is valid and nonblank. Missing or nonnumeric rows are counted and excluded from calculation, without invention/imputation. This is *complete-case*, not pairwise-deletion, analysis.
- Status: `CONFLICT` exit2 when any rows have missing/non-numeric selected values; `UNAVAILABLE` exit3 when correlations are not estimable (fewer than `min_rows` complete cases or zero-variance selected column) without invalid rows; `AGREE` exit0 when all selected data is numeric/complete and pairwise correlations can be calculated; invalid contract/data format exit1. Even `AGREE` means only **calculations valid for supplied source**, not that relationships are stable, statistically significant or causal.
- CPU uses 110-digit Decimal centered deviations and bounded `n * [k(k-1)/2]` arithmetic, with coefficient rounded to six decimal places. A separate `csv.DictReader` independent receipt verifier calculates raw-moment Pearson coefficients from original bytes, rechecks counts/status/SHA256 and rejects altered receipts. `0.7`/ `0.3` strength labels are fixed descriptive thresholds, not calibrated evidence.
- No online API, paid model, LLM inference, arbitrary SQL, code execution, shell or automatic writes. P12 batch/P14 DAG evaluate as HOLD on `CONFLICT`/`UNAVAILABLE`. Source snapshots and goal JSON are both SHA256-checked.

## Verification

Feature + full test evidence must be checked at exact GitHub commit: `python -m compileall -q eai tests`; `python -m unittest discover -s tests -v`; `python -m eai solve-goal examples/sample_csv_relationships_goal.json --json` (expected AGREE / exit 0); `python -m eai doctor --json` (existing 10 bundled probes). P19 dedicated tests use synthesized temporary files; no customer file is checked in.

Windows10/11 native, installed Qwen/Ollama, SearXNG, real customer source, packaging and commercial release **not yet verified**. Retail RELEASE HOLD.
