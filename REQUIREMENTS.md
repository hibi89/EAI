# REQUIREMENTS — EAI final vision and minimal executable

**Priority:** actual personal use. Backend functionality first; design/polish after demonstrated function. Six months to one year or longer is an evolution horizon, not a promised implementation deadline.

## Target product
EAI (Elice Artificial Intelligence) is a free-to-run, independent local-first personal assistant with optional lawful real-time information access. It must gradually combine LLM comprehension with reusable skill/workflow execution, evidence-backed retrieval, deterministic tools, explicit permissions, long-lived memory, and selective strategy learning. HAE/LA and other internal projects remain optional peers.

## v0.1 approved direction / implementation scope
- Python 3.11+ CLI chat via locally installed Ollama/Qwen (model install is an external prerequisite).
- Persistent SQLite conversation history and fetched search snippets, with source/time and finite TTL.
- Explicit opt-in online search via user-operated local SearXNG JSON endpoint; never silently call cloud LLMs or install services.
- Static reusable tool registry; simple local-first routing; warning when freshness cannot be verified.
- Offline unit tests and GitHub CI smoke; measured real Ollama and Windows test is separate.
- No public service, frontend, credential storage, automatic scraping, autonomous file/code modification, model fine-tuning, or integrated LA execution in v0.1.

## Next acceptance milestones
- v0.1: reliable terminal conversation, restart persistence, bounded online search+cache when configured, independent tests on Windows and CI.
- v0.2: source provenance and reliable retrieval, bounded URL/document fetch, robust caching/expiry, improved query router.
- v0.3: permission-scoped local documents, FTS/embeddings RAG with relevance benchmarks; sensitive data never leave machine by default.
- v0.4: versioned reusable workflow templates, optional LA adapter where its actual operations/contracts support the step; no speculative network nodes.
- v0.5+: deterministic validators, bounded concurrent search/solvers, and only then experimental hierarchical search and small ML router with held-out tests.
- v1.0 candidate: useful local UI and deployment; evaluations demonstrate concrete benefit over the simpler baseline, not claims of universal intelligence.

## Nonfunctional requirements
- No paid API as a dependency; respect public data licensing, rate limits and robots/terms as applicable.
- Offline-first, local user data, safe limits/timeout, no network listener, no exposed model endpoint, reproducible backups and migrations.
- Failing online sources must never turn into invented facts. Unverified web snippets are not marked verified.
- Search/LLM outputs are untrusted, never executable as instructions or shell commands.
- Do not train base-model weights on raw internet search results. Evidence and experiment datasets require explicit provenance/licensing review.
