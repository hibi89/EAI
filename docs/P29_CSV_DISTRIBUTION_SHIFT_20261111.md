# P29 — Bounded cohort CSV distribution shift (2026-11-11 KST)

## Choices

- A. Dynamic ML/time-series drift classifier trained on customer histories. Flexible, but training/dependency overhead, calibration risk, false positives and unsupported causal interpretation.
- B. Explicit baseline/current CSV columns, median movement relative to baseline MAD and a separate DictReader/statistics.median verification pass. Selected for deterministic CPU-only bounded evidence, no API/paid compute and straightforward audit.

## Versioned strict contract

```json
{"version":1,"kind":"csv_distribution_shift","goal":"Inspect cohort shift","baseline":"before.csv","current":"after.csv","encoding":"utf-8-sig","columns":["amount"],"min_rows":5,"threshold":"2"}
```

Use `python -m eai solve-goal <approved-goal.json> --json`. The two files must be distinct explicitly selected in-root CSV files, each <=5MiB/20K rows/32 columns, and 1-4 chosen numeric fields. A value that is absent/not a finite fixed-point decimal creates CONFLICT rather than silent imputation. Median and baseline MAD are calculated on complete rows; absolute difference of medians divided by baseline MAD is shown to 6 decimal places. If MAD=0 or too few rows, UNAVAILABLE rather than pretending confidence. A threshold in MAD units 0.5..20 is owner-supplied.

An independent verifier uses a different DictReader/statistics.median path to re-read source and recompute all fields and status; source SHA256 is checked before and after both scans. Output contains only filename, hashes, row counts, aggregate medians/MAD/shift scores; no row values. This is not a statistical significance test, independent sample representativeness or proof of causality.

## Checks and limits

Run exact source Python3.11 full CI, including strict contract/path/tampering/mutation/CP949/negative/status/CLI tests. The feature never executes commands, changes data, calls a model or publishes results remotely. Real customer cohorts, Windows, large datasets and commercial release remain UNVERIFIED / HOLD.
