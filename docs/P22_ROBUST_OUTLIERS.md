# EAI P22 — CPU-only robust anomalies on local CSV (2026-11-10 KST)

Eleventh typed CPU goal: `csv_robust_outliers`. This is a useful **distribution-based anomaly candidate** capability, not the P16 manually supplied minimum/maximum bounds, the P17 schema comparison or the P19 Pearson associations.

## Alternatives considered

- A. Unsupervised ML model (e.g. isolation forest or learned anomaly detection). Could model complex high-dimensional anomalies but requires substantial libraries, parameter tuning, training provenance, false-positive evaluation, security/commercial data validation.
- B. Explicit robust median and median absolute deviation (MAD), per selected numeric column, independent verification from raw CSV. **Selected**: finite bounded deterministic CPU, no training/privacy upload, simple to explain and reproduce; limitations on zero-MAD or multimodal distributions are explicit.

## Input contract

```json
{
  "version": 1,
  "kind": "csv_robust_outliers",
  "goal": "Inspect unusual sales",
  "source": "sales.csv",
  "encoding": "utf-8-sig",
  "columns": ["revenue", "expenses"],
  "min_rows": 5,
  "threshold": "3"
}
```

Example: `python -m eai solve-goal examples/sample_robust_outliers_goal.json --json`. The bundled synthetic CSV contains one intentionally large value in `revenue` (record 6) and returns `CONFLICT` / CLI exit 2 by design.

## Numeric policy and safety

- Each selected value must be a finite fixed-point decimal string (<=24 integer digits and <=12 fractional digits); up to 4 selected numeric columns. `min_rows` integer 5–20,000, threshold as a decimal **string** between 1 and 20.
- Maximum owner-selected CSV 5 MiB, 20,000 records, 32 columns, 4,096 characters/cell. Goal-relative file path only, symlink escape prevented, allowlisted encoding `utf-8-sig`, `utf-8`, `cp949`.
- Use **complete cases** across all selected columns, without imputation. Report invalid/missing row counts separately. For each column calculate median `m`, MAD = median(|x−m|); if MAD > 0, flag rows where `|x−m|/MAD > threshold`. This is an unscaled MAD score; it is **not** the usual Gaussian-consistent scaled robust z-score. A threshold of 3 is a user choice, not proof of a universal error rate.
- Report only input column name, median/MAD aggregate, counts, and up to 10 candidate record indices (ordered column-first and within column row-first). Never output individual source values, sensitive record keys or direct file contents.
- `AGREE`/exit0 means no candidates in estimable complete numeric data; `CONFLICT`/exit2 means any candidate or missing/nonnumeric selected data; `UNAVAILABLE`/exit3 means too few usable samples or any zero-MAD column with no prior conflict. This is an advisory quality signal, not a business rule or evidence of fraud.
- Primary solver uses csv.reader and Decimal (110-digit context), with before/after SHA-256. Independent verifier uses csv.DictReader and statistics.median with multiplication-based threshold comparison, checks exact report fields and source hash. P12 SHA-pinned batches/P14 dependency DAG automatically gate downstream work on `CONFLICT`/`UNAVAILABLE`.
- No automatic repair, data upload, arbitrary code/SQL, external API, paid AI or GPU. Actual customer data, Windows 10/11, live Qwen/Ollama/SearXNG, packaging, licenses and retail distribution remain unverified.

## Acceptance

Commit exact feature/test SHA, perform Python 3.11 Linux `compileall`, full unittest suite and CLI smoke. P22 synthetic fake data unit/integration tests cover outlier/normal/zero-MAD, shape, privacy, provenance, CLI status, batch/pipeline, tamper rejection and encoding. Do not increase completion on source-only commits; evaluate only after full CI succeeds.

## Exact-source verification record

- First source `623089274393a5a86ce323a26877608f143b15b5` [Actions 42696138434](https://github.com/hibi89/EAI/actions/runs/42696138434): 475 tests attempted / 11 ERROR + 1 FAIL. Root cause: primary scanner destructured a `tuple[Decimal,...]` as if one Decimal; TypeError in `abs(value-center)`. All failures followed this bug.
- Corrected and verified exact source+tests SHA **`88af3412d59dad8ea848322bdb75292adb7db9e4`** [Actions 42696296697](https://github.com/hibi89/EAI/actions/runs/42696296697) Ubuntu Python3.11 **475/475 PASS / 0 FAIL / 0 SKIP**, syntax/CLI smoke PASS, P22 +19 tests. Do not infer actual customer dataset validity or Windows/retail release.
