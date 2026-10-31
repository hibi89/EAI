# STATUS — EAI P4 (2026-10-31 KST)

## Product / scope
Private `hibi89/EAI`, development branch `feature/local-first-mvp`; `main` and HAE/LA/other project sources preserved. Final goal: independent EAI CPU reasoning/planning/verifying/answer engine, optional Qwen used for **input parsing only**; GPT-class autonomy remains future research, not current capability. No paid API, GPU or remote service required for P4.

## Source milestone
- `18da5701ae0262607f397b54e873b4b50cfeff2f`: added `eai/reconcile_csv.py`, `reconcile-csv` CLI, `tests/test_reconcile_csv.py`, and synthetic `examples/sample_sales_source_b.csv`.
- This document's publication is a later commit. Read the real GitHub branch HEAD before resuming; never guess the final SHA.

## Delivered and verified
- P0 exact arithmetic, Qwen IntentSpec-only optional parser, opt-in SearXNG/SQLite cache.
- P1 CPU-authorized local notes, SQLite persistence and pre-migration backups.
- P2 bounded CPU numeric comparison + read-only CSV profile.
- P3 single-file CSV numeric claim VERIFIED/CONFLICT/UNAVAILABLE with source SHA256.
- **P4 keyed two-source CPU reconciliation**, counts equal/mismatched keys, left-only/right-only, nonnumeric values; absolute tolerance, SHA256 before/after, 20-detail bounded output, JSON, exit 0 AGREE / 1 ERROR / 2 CONFLICT / 3 UNAVAILABLE. Duplicate content hashes explicitly not independent evidence.
- Local Linux Python 3.13.5: `python -m compileall -q eai tests` PASS; `python -m unittest discover -s tests -v` **97 PASS / 0 FAIL / 0 SKIP**. Example two files total 352 each but individual yearly values differ and produce CONFLICT.
- P4 four source Git Blob SHA values exactly match GitHub readback. P3 zip/remote has five older blob differences: **whole byte-identical checkout not verified**.

## Blockers and unknowns
- GitHub Actions run `41204686535` for P4 source `18da5701`: completed **FAILURE**, job has no steps and runner_name empty; ~2 second execution. Root cause unproven; same pre-step failure repeats. Do not call CI green, and do not trigger pointless identical reruns.
- User Windows 10/Python 3.11 native execution, real Ollama/Qwen structured input, real SearXNG, CPU/GPU benchmarks: UNVERIFIED.
- There is no deployment or Vercel Production URL (NOT APPLICABLE).

## Next priorities
1. Verify complete exact-remote tree in a native environment (full 97+ suite) and Windows CLI when possible.
2. Diagnose missing GitHub Actions runner steps from meaningful job/account evidence; do not modify billing or security settings without approval.
3. Improve source matching based on real user data (additional metrics/provenance, user-controlled keyed aggregation) with fresh regression tests.
4. Extend EAI cognitive solver library only when it proves independent usefulness; frontend and LA integration remain later phases.

This STATUS accurately distinguishes local synthetic evidence from live real services, original-data authentication, and general intelligence.
