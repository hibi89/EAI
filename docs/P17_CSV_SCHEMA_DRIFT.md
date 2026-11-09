# EAI P17 — independently verified local CSV schema drift detection

2026-11-10 KST. Sixth typed CPU goal: `csv_schema_drift`.

## Design alternatives
A) Compare only header arrays of two CSVs: minimal CPU cost but misses numeric/text schema changes and empty-column uncertainty.
B) Compare ordered headers and bounded per-column numeric/text/empty evidence, with separate `csv.DictReader` verification. Chosen; O(rows × columns) on two explicit local files, no dependencies beyond stdlib and zero external calls.

## Contract
`{"version":1,"kind":"csv_schema_drift","goal":"Check schema","baseline":"sample_drift_baseline.csv","current":"sample_drift_current.csv","encoding":"utf-8-sig"}`

Both source files must be different, explicitly selected relative paths within the goal file's directory, no absolute/parent/symlink escape. Each CSV <=5MiB, <=20,000 records, 1–32 unique nonempty headers, <=4,096 chars per field. UTF-8/UTF-8 BOM/CP949 allowed.

Reports added/removed header names, reordered header order when names unchanged, and inferred numeric/text/mixed/empty types for shared columns, with numeric/text/missing counts and both exact SHA256 digests. Does **not** emit row data/keys or infer business correctness from types. Order is a schema difference only when both column name sets are equal. Differences => CONFLICT; no changes but one header-only file or all-empty observed columns => UNAVAILABLE; otherwise AGREE. Different **row counts alone** are not considered schema drift. A valid AGREE is not proof that a supplier's contract or values are correct.

An independent guard rescans each original file through a different DictReader implementation, recomputes all counts, type/order changes and source hashes, and rejects forged reports. The result integrates into `solve-goal`, P12 batch, P14 dependent pipeline (CONFLICT holds downstream), P15 manifest builder and P13 doctor (ten checks with this synthetic fixture). Existing source/memory data untouched, stdout only, no networking, no LLM or privileged operations.

## Commands and verification
`python -m eai solve-goal examples/sample_csv_schema_drift_goal.json --json`
Expected sample status CONFLICT and exit 2. `python -m unittest discover -s tests -v`.

## Caveats
Inferred types are derived only from currently observed values; missing or synthetic data can mislead. Actual Windows10/11, real customer files, Qwen/Ollama, SearXNG and commercial release remain unverified.
