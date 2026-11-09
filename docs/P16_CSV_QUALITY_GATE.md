# EAI P16 — independently verified local CSV quality gate

2026-11-10 KST. Native fifth typed CPU goal: `csv_quality`.

## Design choice
- A. Extend the existing single CSV numeric profiler with a human-facing warnings list, without a second evaluation. Faster to implement, but an incorrect count could be displayed as evidence.
- B. Bounded record-wise rule scanner, with **independent column-oriented rescan** that validates original SHA256, exact result counts and first sample record indices. Chosen: stable safety/accuracy cost, no extra dependencies, no external service, O(rows × rules) with 20,000-row/5MiB cap.

## Strict contract / safety
`{"version":1,"kind":"csv_quality","goal":"Review synthetic CSV","source":"sample_quality.csv","encoding":"utf-8-sig","required":["rowid","amount"],"unique_by":["rowid"],"numeric_rules":[{"column":"amount","min":"0","max":"1000"}]}`

- File must be within the JSON goal's own directory; cross-directory `..`, absolute and symlink escapes, binary invalid encoding, invalid/missing/duplicate CSV headers are rejected. Goal itself <=64KiB, CSV <=5MiB, <=20,000 records, <=32 columns, <=4,096 characters per cell. Maximum 8 required columns, 3 key columns, 8 numeric fixed-point rules. No dynamic expressions/eval.
- Missing required entries, repeated nonempty composite key, nonnumeric data, below-min, above-max are counted. Missing optional numeric values are not silently represented as zero; if the numeric column is required the missing rule is counted separately.
- Display includes **only row record indexes, column headers and issue categories**, never raw cell values or unique key values; examples maximum first 10 violations. Record index means 1-based data record, not physical line number when quoted multiline cells exist. Source filename and SHA256 are shown.
- `AGREE` if nonempty records meet all rules; `CONFLICT` if any rule violation, `UNAVAILABLE` if header-only file. This is not a guarantee that the dataset is factually correct or complete.
- Standalone typed goal can be run via P7 `solve-goal` and composed into SHA256-pinned P12 batch, P14 DAG pipeline and P15 generated manifests; existing `REVIEW` policies prevent downstream goals automatically proceeding after conflict.
- No files modified, no external data/model calls, no billing/permission changes. Full source rehashed after each scan, including independent verification.

## Commands
`python -m eai solve-goal examples/sample_csv_quality_goal.json --json`

Exit code 2 = CONFLICT (expected for synthetic example), 0 = AGREE, 3 = UNAVAILABLE. P13 doctor automatically checks sample CONFLICT as its **ninth** offline check.

Tests: `python -m unittest discover -s tests -v`; `python -m compileall -q eai tests`.

## Unverified / next gates
Real Windows 10/11, owner-provided customer CSV, actual Qwen/Ollama, local SearXNG, GUI, field semantics and commercial release remain unverified. All input constraints are owner-entered and must be validated against domain expectations.

## P16 CI acceptance (2026-11-10 KST)

- Initial final P16 code/test SHA `954b72737338082d1d5ce5c327f5be29c96732ef` [Actions 42679425913](https://github.com/hibi89/EAI/actions/runs/42679425913) **348/348 PASS**; final subsequent P17 code/test SHA `9b0b7438cd0e8756e87c7ca4d03d23a731773d91` [Actions 42680542935](https://github.com/hibi89/EAI/actions/runs/42680542935) **375/375 PASS**, same P16 28 tests retained and full regression green. Doctor checks 9 then 10 after P17.
- Customer CSV semantics and Windows native execution remain unverified, and sample values are synthetic. No general truth claims.
