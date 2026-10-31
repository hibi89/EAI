# STATUS — EAI

Updated: 2026-10-31 KST, based on GitHub evidence.

## Project
EAI / Elice Artificial Intelligence; private repository hibi89/EAI. Chief role accepted by ChatGPT at owner request. Trunk main initialized at 09f3f8be2dab2d1aa8096c0d6d439f8fc6e48960; development branch feature/local-first-mvp. Full architecture is documented in docs/ARCHITECTURE.md. Actual owner usage, not speculative full-vision completion, drives priorities.

## Confirmed
- User's private EAI repository exists; branch feature/local-first-mvp created.
- Source baseline commit a945499f34a0938b2151081651de372d1646da95: local CLI, Ollama loopback chat connector, SQLite memory, opt-in SearXNG search with TTL cache, registry, offline test code and CI YAML.
- Reviewed HAE feature/lightning-azent engine and docs: current inspected runtime is local/synthetic and does not support external HTTP request nodes; no LA/HAE source copied or mutated.

## Not yet proved
- Python unit tests and CI *completion* not yet confirmed for this branch.
- Real Windows / Ollama / Qwen / SearXNG interactions are not tested in this environment. No deployment or external calls performed.
- Full RAG, parser-based verification, LA integration, hierarchical search, strategy ML, native frontend and production hardening remain future work.

## Next: P0 gate
1. Verify branch HEAD, code syntax and offline tests (CI + direct runtime where available); fix any actual failures.
2. Verify real Ollama on user's Windows when available, without requiring new GPU purchase; log model/version/hardware and result.
3. Verify online query only after owner configures and approves local SearXNG setup; never auto-transfer personal prompts.
4. Use first owner sessions to prioritize basic errors before adding plugins or UI.

See docs/ACCEPTANCE.md for definitions. Deployments: not applicable; no Vercel or public URL.
