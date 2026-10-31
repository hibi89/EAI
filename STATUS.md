# EAI — STATUS (2026-10-31 KST)

## Product and phase
EAI (Elice Artificial Intelligence) is a private, CPU-first **independent cognitive engine**: Qwen, if enabled, **only classifies user input** into IntentSpec. EAI itself routes the task, calculates or retrieves evidence, verifies input bounds, renders the answer, and writes SQLite history. Final vision is longer-term research (hierarchical search, strategic ML, independent generalization), **not implemented or claimed at P0**. Canonical direction: ADR-0002; compute research: ADR-0003.

## Repository and immutable milestone
- Owner: hibi89/EAI (private)
- Branch: feature/local-first-mvp
- Tested-source publication commit: ed55e7d2918fd576ce587ce330d32e5e5c1c9123
- Main is the preserved bootstrap branch; existing HAE/LA/DBVORA/SOVIA repositories were not modified.
- Before a new change, read HANDOFF → STATUS → AGENTS → REQUIREMENTS → actual source.

## Implemented
- Independent CLI: `python -m eai ask '계산 12*(3+4)'`; `python -m eai chat`; `python -m eai health`.
- Python 3.11+ standard library: CPU rule parser; optional Ollama/Qwen structured input parser with strict IntentSpec v1 JSON schema; CPU_ECO parser mode uses `num_gpu=0`.
- Independent CPU CognitiveEngine: bounded exact arithmetic (Fraction/Decimal), fixed answer renderer, honest unsupported responses.
- Registered, consent-gated `research.web.v1` workflow via optional local SearXNG JSON interface; SQLite cached source list and local recall, all source snippets UNVERIFIED.
- SQLite local conversation history; token/model/source binaries and database files excluded from Git.
- Original obsolete OllamaChat answer synthesis path disabled; existing previous commit allows source recovery.

## Verified in this turn
- Local Python 3.13.5: `python -m compileall -q eai tests` PASS.
- `python -m unittest discover -s tests -v`: **21 PASS / 0 FAIL / 0 SKIP** (offline mocked provider, not live services).
- CLI: health PASS; CPU arithmetic `1250000*0.12=150000`, `0.1+0.2=0.3`, `200*(1+0.15)=230` PASS.
- ZIP independent extraction, 21 tests again PASS; separate CLI processes wrote SQLite with 4 turn records and reopened it PASS.
- GitHub connector fetch confirmed changed file blobs in P0 commit match local Git hashes; source and ADR-0003 presence verified.

## Unverified / blocked / not implemented
- GitHub Actions final conclusion UNVERIFIED (combined statuses empty; PR-run lookup empty; this is not a CI failure proof).
- User's actual Windows 10/Python 3.11 local Ollama Qwen structured classification **UNVERIFIED**; no model is installed automatically.
- Real SearXNG search / public provider reliability **UNVERIFIED**; network query requires explicit `--online`.
- General GPT-class reasoning, hierarchical search/ML, RAG, adaptive CPU/GPU golden ratio, LA adapter, graphical UI, production deployment: NOT IMPLEMENTED.
- Ollama compute profiles: CPU_ECO and OLLAMA_DEFAULT only, **no real performance benchmark**.

## Next actions (priority)
1. Check GitHub branch check-run/CI result with a tool that actually lists Actions check runs; run a fresh byte-identical checkout on Windows 3.11.
2. Run the real Qwen input-only path when available, verify strict parse/fallback and no unauthorized answer generation; do not require a GPU purchase.
3. Only with consent, verify local SearXNG JSON search, cache/staleness, provider limitations and privacy.
4. Add the next narrow task solver based on actual owner use; do not substitute large model generation or UI work.
5. Benchmark CPU/GPU parser offload on the owner's hardware, compare static profiles; do not invent a fixed optimal split.

Production URL/Vercel: **N/A** (local executable CLI). No paid service or external model/credentials submitted by this run. No promise of unattended two-day work.
