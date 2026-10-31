> **P2 progress, 2026-10-31:** Added `compare` CPU numeric solver and `analyze-csv` read-only streaming profiler. Local 55 unit/integration tests PASS; exact modified source blobs match GitHub staging. Real Windows, real Ollama, real SearXNG and GitHub Actions success remain separate gates. Next: full byte-identical remote checkout, Windows smoke, then local dataset schema/quality inspection driven by actual owner use. No priority shift to frontend or claims of GPT-equivalent reasoning. Details: [P2_CPU_ANALYSIS](P2_CPU_ANALYSIS.md).

> **P0 implementation evidence — 2026-10-31:** Locally implemented IntentSpec + CPU rule fallback + QwenIntentParser (input only), independent CognitiveEngine, exact bounded arithmetic, evidence retrieval, deterministic renderer, CLI. The local Python 3.13.5 working tree passed 21/21 offline tests and CLI calculation smoke. Next gates: exact remote SHA CI; owner's Windows Python 3.11 and Ollama structured-parse smoke; live SearXNG only with explicit permission. Adaptive CPU/GPU remains an unmeasured R&D candidate [ADR-0003](ADR-0003_ADAPTIVE_CPU_GPU_RESEARCH.md). Frontend remains later.

> **Priority override, 2026-10-31:** [ADR-0002](ADR-0002_EAI_COGNITIVE_OWNERSHIP.md) changes the next development task: before treating v0.1 as usable independent EAI, implement IntentSpec parser boundary (Qwen solely here), EAI ProblemSpec/TaskGraph/ResultSpec independent solver on one narrow task, and EAI deterministic renderer. Existing general Ollama-chat MVP source is nonconforming and must not be shown as completed EAI intelligence. Keep offline acceptance and backward-compatible data preservation.

# EAI roadmap — use-driven, backend-first

## Phase P0: reproducible local core (NOW)

- [x] Initialize private GitHub repository + isolated feature branch.
- [x] Implement local Ollama CLI adapter and SQLite memory source.
- [x] Implement ToolRegistry + optional SearXNG search/caching path and offline test suite source.
- [x] Implement fixed reusable research.web.v1 workflow template with permission gate.
- [x] Run preliminary reconstructed-mirror offline tests: 15 PASS / 0 FAIL with Python 3.13.5 (not byte-identical; not CI evidence).
- [ ] Verify exact GitHub source CI, actual Windows Python 3.11 CLI, real Ollama local inference, restart persistence.
- [ ] Verify real SearXNG search with user-enabled JSON interface and query privacy.

## Phase P1: make v0.1 usable every day

- Bound memory growth, summarize context without losing raw history, handle model-not-found cleanly, run crash/restart test and backup/restore, measure 3B model performance on available PC.
- Improve CLI usability only where actual owner sessions expose friction. No frontend redesign.

## Phase P2: reliable online evidence + offline documents

- Cache provenance, TTL and content hashes; validate domain/source dates and source contradictions; add local FTS then optional Ollama embeddings, permission-scoped file indexing.
- Add GitHub Releases/official REST, RSS, news and technical documentation as reusable skills. Evaluate free provider policies before use.

## Phase P3: reuse workflows and LA safely

- Versioned template registry with bounded parallelism, retry and cancellation. EAI local workflow runner first; a typed LA adapter only if compatible LA contracts are proven against its current code and tests.
- Preserve existing HAE source; no direct modification until explicit owner approval.

## Phase P4: deeper problem-solving

- Deterministic verification and bounded solver dispatch; hierarchical search for suitable problems; small ML router only after labeled execution outcomes and held-out baseline; no fantasy performance claims.
- Privileged tool actions require approvals, scoped file capabilities and evidence ledger.

## Phase P5: user-facing polish/release

- Local authenticated UI after stable CLI, OS portability, security review, packaging, license review, reproducible setup and full real E2E.

## Execution discipline

At each phase: reproducible failing case → minimum code change → unit+integration tests → remote SHA/CI status → actual owner environment verification when possible → STATUS/HANDOFF. If a task reveals genuine user friction, reprioritize instead of following a speculative feature list.
