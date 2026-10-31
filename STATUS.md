# STATUS — EAI P5 (2026-10-31 KST)

## Current canonical branch
- Private repository: `hibi89/EAI`, branch `feature/local-first-mvp`, main remains preserved. P5 code milestone `bd1055cd5b06d9862a1541bb9acfcf546252b894`; read latest branch SHA after docs commit.
- Owner-approved design ADR-0002: Qwen classifies user input **only**. CPU EAI code owns calculation, search permission, validation, data comparison and final deterministic response. GPT-class general cognition is a long-term aspiration, **not achieved**. No LA/HAE source or settings changes.

## Implemented
- P0 exact arithmetic, strict IntentSpec, optional local Qwen input parser, opt-in SearXNG, SQLite history/cache.
- P1 user-authorized local notes, recall and pre-migration database snapshots.
- P2 exact numeric comparison and bounded read-only CSV profiling.
- P3 CSV numerical claim vs local source: VERIFIED/CONFLICT/UNAVAILABLE.
- P4 two-source keyed CSV reconciliation, hash evidence and missing/nonnumeric distinctions.
- **P5** `diagnose-csv` multi-field (1–8) keyed discrepancy diagnostics, per-field full counts, 20-key bounded candidate evidence, suspected data-coverage/version/value-format categories. **No proof of real causal origin or source correctness**. Explicitly selected read-only files; no cloud/LLM/GPU dependency.

## Actual verification
- Python 3.13.5 Linux: compileall **PASS**; 122 offline unittests **PASS / 0 FAIL / 0 SKIP** (97 preserved + 25 P5). P5 CLI returns CONFLICT/exit 2 for sample files sharing totals 352/35 but differing 2024/2025.
- New/modified 4 P5 source files have GitHub blobs matching local Git SHA; full historical repository byte-identical tests still UNVERIFIED because unchanged local P4 mirror differs from some GitHub blobs.
- Synthetic performance: 20k rows × 8 numeric columns, ~3.1s **in this container only**, no device-wide CPU/GPU tuning claims. Original sample file bytes unchanged.
- GitHub Actions P5 source run `41206281818` completed **FAILURE** (no runner name, zero job steps, ~2s). Prior runs same pattern; cause unproven, no claimed CI PASS and no blind reruns.

## Remaining
Actual owner's Windows 10 + Python 3.11 environment, real optional Qwen/Ollama, optional SearXNG, source authenticity and real user CSV datasets: UNVERIFIED. Independent broad cognition, RAG, ML strategy learning, LA adapter, GPU scheduler and frontend: NOT IMPLEMENTED. Vercel Production URL and project: NOT APPLICABLE (local CLI).

## Next
1. Verify a complete byte-identical remote checkout and actual Windows 3.11 CLI when accessible.
2. CI failure: inspect actionable GitHub Actions account/runner evidence; do not change permissions/billing or repeatedly trigger same failing job without reason.
3. Add next independent CPU reasoning/verification capability based on user usefulness, without pretending that specialized tools imply universal GPT-class intelligence.
4. Update STATUS/HANDOFF after verified code changes; preserve data and original branches.

Docs: `docs/P5_MULTI_METRIC_DIAGNOSIS.md`. This status records measured local results and unknowns, not a production signoff.
