# EAI — STATUS (2026-10-31 KST)

## Canonical objective and active branch
- Private repository `hibi89/EAI`, branch `feature/local-first-mvp`; `main` remains preserved, no force-push.
- EAI must own solving/verification/response generation; Qwen (optional) is ONLY a natural-language input classifier. GPU is not required for explicit CPU commands. See ADR-0002 and ADR-0003.
- P2 source milestone: `d903b1247d218e924f956cd630cf45fe8290cf44` (CPU compare and CSV code with 9 changed/new files). Documentation SHA is the current branch HEAD after publication.
- Existing HAE/LA/SOVIA and deployment settings untouched.

## Implemented (P0/P1 preserved + P2)
- P0: CPU exact arithmetic, strict IntentSpec, optional Qwen parser with CPU rule fallback, permission-gated SearXNG lookup, SQLite history and cache.
- P1: literal `기억해` note write, note list/recall, duplicates blocked, legacy SQLite snapshot before additive migration.
- P2: `비교 A=100,B=120,C=114` exact Decimal-based ranking, extrema/gap and sequential changes; invalid or ambiguous inputs rejected. Percentages suppressed when previous value <=0. Explicit recognized commands bypass Qwen even when configured.
- P2: `python -m eai analyze-csv examples/sample_sales.csv` read-only local CSV summary: rows/columns, missing counts, numeric sum/min/max/mean with UTF-8/CP949 options. File size <=5MiB, rows <=20k, columns <=32, fields <=4096 chars. No file writes/uploads or SQLite storage of CSV rows.
- Synthetic read-only example CSV provided. UI remains deliberately deferred.

## Actual verification
- Local container Linux Python 3.13: `python -m compileall -q eai tests` PASS; `python -m unittest discover -s tests -q` **55 PASS / 0 FAIL / 0 SKIP**.
- CLI subprocess: compare `2023=100,2024=125,2025=110` gives 25% then -12%; `계산 0.1+0.2` returns 0.3; original note store/retrieve still works; `analyze-csv` sample returns correct sales sum 352, mean 117.333333.
- All 9 P2 source file blob SHAs compared against local Git and GitHub file readback: exact MATCH. `storage.py` and `tests/test_memory.py` in the local prior P1 package differ in formatting from GitHub, so **full GitHub-checkout 55 PASS is not claimed**.
- Tests include malformed input, duplicate labels, large exact values, negative/zero baselines, no Qwen for explicit tasks, privacy/no-network, CSV row/field/bounds, UTF-8/CP949 and previous simulated HTTP/SQLite operations.

## GitHub CI / real hardware
- Latest P2 code run `41202155968`, SHA `d903b124...`: **FAILURE**. Job steps `[]`, runner name empty, started and completed within seconds. Earlier runs similarly failed. Root cause unknown; does not establish code failure or CI PASS. Avoid repeat no-op reruns; inspect GitHub Actions account/repo UI, permissions/billing/runner logs with owner's approval if needed.
- Actual Windows 10 / Python 3.11, real Ollama/Qwen model, public SearXNG provider, CPU/GPU offloading, full GitHub clone and hosted production **UNVERIFIED**. There is no Vercel project/URL (not applicable).

## Next (priority)
1. Verify exact remote checkout on Windows Python 3.11 when available; offline test and read-only P2 CSV demo on actual PC. Diagnose GitHub Actions pre-step failure through actionable runner logs rather than speculative code changes.
2. Extend read-only CSV analysis for actual owner workflows after collecting feedback; do not ingest private files remotely without consent.
3. Add the next narrow deterministic solver or local document/knowledge retrieval based on real use; retain CPU-first policy and Qwen input-only boundary.
4. Evaluate SearXNG and Qwen on owner hardware as opt-in external prerequisites, then profile CPU/GPU allocation with real measurements. No fixed ratio claim.

Last document update: 2026-10-31 KST. Code SHA as above; documents published on later branch HEAD. All unverified conditions are separate completion gates.
