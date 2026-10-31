# AGENTS — EAI chief and engineering contract

Date: 2026-10-31 KST. Owner appointed this ChatGPT instance as EAI chief. Continue with `HANDOFF.md` → `STATUS.md` → `AGENTS.md` → `REQUIREMENTS.md` → code.

## Purpose
Deliver a useful personal local AI first and evolve over 6–12+ months by actual daily use. Design for extensibility without blocking on speculative deep reasoning, UI polish or network services.

## Execution authority and boundaries
- EAI is private, independent, and **local-first**. Never claim model weights learn by adding a document to SQLite; distinguish cache, retrieval, tuning and proof of improvement.
- `main` remains safe; develop on `feature/local-first-mvp`, verify actual HEAD/test output before merge. No force push, no secret files or source-data commits.
- No changes to HAE/LA/DBVORA/SOVIA repositories without owner approval. Inspect their contracts only. Never copy n8n or third-party code into EAI without license and provenance review.
- Before significant scope or paid service, system permission, security policy, original-data modification, sensitive external transfer, or model training: compare at least two designs and obtain owner approval.
- For approved implementation: core logic → safe local tests → real local inference/search checks → stability/security → CLI ergonomics → UI last.
- Record actual test results with SHA and separate PASS/FAIL/SKIP, synthetic checks and real-model E2E. No fake success; stop-and-pivot after two ineffective approaches.
- User can type 'ㄱ' to resume the next safe task. After substantive changes, refresh STATUS/HANDOFF together, with concrete next action and blockers.

## Architecture ownership
- EAI core owns chat, routing, tool contracts, memories and evidence. It must work without LA or HAE.
- Optional LA integration uses a **versioned adapter**, not a direct dependency or imported unverified network node. HAE is a distinct product and is not the EAI UI.
- Defaults: no external API fees; no network listener; local filesystem SQLite; offline conversation; explicit opt-in for any online retrieval; bounded GET-only local SearXNG initially.
- Learn user feedback by recorded signals first, not automatic web-content fine-tuning.

## Acceptance gates
See docs/ACCEPTANCE.md for offline tests, Windows/Ollama checks, SearXNG live path, crash/restart continuity, privacy, and performance baseline. A code commit is only a *source* milestone.
