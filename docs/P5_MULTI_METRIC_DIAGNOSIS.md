# P5 — EAI CPU multi-metric CSV discrepancy diagnostics

Updated 2026-10-31 KST. Source milestone: `bd1055cd5b06d9862a1541bb9acfcf546252b894`.

## Product scope

EAI's own deterministic code locates **which CSV keys and fields disagree**, gives bounded evidence and **possible investigation targets**. It never decides which source is true or proves the cause of mismatch. No Qwen inference, GPU, paid API, network, local-file modifications or HAE/LA changes.

## Design alternatives

- A. New single-pass general multi-column CSV parser: possibly faster on large workbooks, but duplicates P4 CSV validation/hash/decimal logic and increases maintenance and regression risk.
- **B. P4 `reconcile_csv` re-used independently per metric (chosen):** preserves existing input and evidence gates with less code; each metric re-reads each source. Bounded to 8 metrics and 20k rows per file. Benchmark or refactor if user workloads later justify.

## CLI

```powershell
python -m eai diagnose-csv examples/sample_sales.csv examples/sample_sales_multi_drift.csv --key year --values sales orders
python -m eai diagnose-csv examples/sample_sales.csv examples/sample_sales_multi_drift.csv --key year --values sales orders --json
```

The supplied synthetic files have equal total sales (352) and orders (35), but differ on 2024 and 2025 across both metrics. These are synthetic example records, not real business evidence.

## Contract and limitations

- `--key`: unique column present in both CSVs; `--values`: 1–8 unique numerical columns, separate from the key; `--tolerance`: one **absolute** nonnegative decimal tolerance shared by fields. A shared nonzero tolerance is not generally comparable across different units.
- Same P4 input limits: each CSV ≤5MiB, ≤20,000 rows, ≤32 columns, ≤4,096 chars/field; UTF-8/UTF-8-SIG/CP949 supported; exact Decimal comparisons and no inferred units/dates.
- Per-metric full counts are reported. P4 exposes only first 20 keyed details per metric, while P5 displays at most 20 combined candidate keys. When detail is truncated, **candidate ranking is a sample, not complete**. Relative rank uses number of affected fields and event type, never absolute differences between incomparable units.
- Hypothesis tags: `MULTI_METRIC_DRIFT`, `SINGLE_METRIC_DIFFERENCE`, `KEY_COVERAGE_DIFFERENCE`, `VALUE_TYPE_ISSUE`. They are *inspection prompts*, not proof of error cause or attribution to file A/B.
- Returns `AGREE` (exit 0) for eligible nonempty agreement, `CONFLICT` (exit 2) for discrepant numbers/keys, `UNAVAILABLE` (exit 3) for missing/invalid evidence, duplicate content hashes, or empty eligible sets, and input/IO error (exit 1). Conflicts take precedence over unavailable fields.
- SHA-256 of each selected file is compared across passes and again before completion; this is drift detection, **not** an atomic filesystem snapshot, trusted signature or authentication. A report may contain sensitive keys: it must remain on the user's PC unless separately approved for transfer.

## Verified evidence and pending gates

In this environment Linux Python 3.13.5: `python -m compileall -q eai tests` PASS and `python -m unittest discover -s tests -q` **122 PASS / 0 FAIL / 0 SKIP**, including 25 new P5 cases. Actual local CLI and read-only file hashes checked, synthetic 20k rows × 8 columns runtime ~3.1s on this container (not user hardware). Four P5 source blob SHAs matched GitHub after publication. Existing historical differences in unchanged local vs GitHub files mean full byte-identical repo regression is UNVERIFIED. GitHub Actions run `41206281818`: FAILURE, job steps=[], runner_name empty; no actual CI test result established. Windows Python 3.11, Qwen, SearXNG, adaptive CPU/GPU and public release NOT VERIFIED/NOT APPLICABLE.

Next: exact-source testing and usable Windows smoke, then independent EAI reasoning beyond specialized CSV tooling. Do not overstate GPT-level ability.
