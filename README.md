> **2026-10-31 architecture correction — read first:** [ADR-0002: Qwen is only the input parser/classifier; EAI itself owns problem-solving, planning, verification and final response.](docs/ADR-0002_EAI_COGNITIVE_OWNERSHIP.md) The existing Ollama-chat-generates-the-answer implementation is a provisional *nonconforming* baseline; do not claim it matches the final EAI design. No code was changed by the correction.

# EAI — Elice Artificial Intelligence

**Local-first personal AI**. Private owner-led long-term project. This repository starts with a deliberately small, executable **Python CLI**, not a web UI or a self-trained foundation model.

## Status (2026-10-31 KST)

- Development branch: `feature/local-first-mvp`; the `main` branch is only an initialization marker. Do not merge without verification.
- Source has been committed: local Ollama chat, local SQLite conversation/search cache, opt-in local SearXNG search, tool registry and a fixed research.web.v1 workflow, offline tests.
- **Preliminary mirror verification:** 15/15 offline tests PASS and CLI/compileall smoke PASS on Python 3.13.5 local reconstruction (not byte-identical with GitHub source). **Not yet verified:** exact GitHub branch CI conclusion, actual Windows + Ollama/Qwen inference, live SearXNG search. This is not a customer-ready release.
- No HAE/LA source was copied, modified, or required to run this branch.

## Start here (Python 3.11+, no Python runtime packages required)

1. Install Ollama through its official installer; explicitly download the model before first use: `ollama pull qwen2.5:3b`. This download consumes network bandwidth/disk; there is no paid API requirement.
2. Ensure local Ollama responds at `http://127.0.0.1:11434`; run `ollama serve` if needed, without opening it to your LAN.
3. From this branch's repository root:

```powershell
python -m eai health
python -m eai ask "안녕, 너는 누구야?"
python -m eai chat
python -m unittest discover -s tests -v
```

Old PCs can choose a smaller, locally installed model by passing `--model <model-tag>` before `ask` or `chat`. CPU inference may be slow. A machine without Ollama/model cannot perform real inference; this is **not an offline fallback model**.

## Optional free online lookup (not enabled by default)

Start a trusted **local** SearXNG instance with JSON output enabled, then opt in per CLI session:

```powershell
python -m eai --searxng-url http://127.0.0.1:8080 --online ask "오늘 발표된 AI 모델은?"
```

SearXNG must be set up separately. The local SearXNG service may forward the search query to external engines, so it **is not an offline/private lookup**. The CLI does not install or enable it on your behalf. Sources are labeled UNVERIFIED; cached snippets are not independent fact checking. Search may fail because of provider throttling, instances, missing JSON API support, or network connectivity.

## Long-term objective

- Reusable tool / skill registry, templated workflows, safe optional Lightning Azent adapters.
- Offline/online retrieval, provenance, semantic RAG memory, cross-source deterministic validation.
- Hierarchical problem decomposition, bounded parallel solvers, small learned strategy router evaluated against explicit baselines.
- Approval-based local automation; original data preservation; no silent uploads, model retraining, or privileged system changes.
- Native local UI after backend functionality and tests; not an early blocker.

Primary documents: [Architecture](docs/ARCHITECTURE.md) · [Interfaces](docs/INTERFACES.md) · [Roadmap](docs/ROADMAP.md) · [Acceptance](docs/ACCEPTANCE.md) · [Security](docs/SECURITY.md) · [Requirements](REQUIREMENTS.md) · [Handoff](HANDOFF.md).
