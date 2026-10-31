> **SUPERSEDED in part by owner on 2026-10-31:** [ADR-0002](ADR-0002_EAI_COGNITIVE_OWNERSHIP.md) takes precedence over this earlier architecture wherever it describes Qwen/Ollama as the final answer generator. New authoritative flow: Qwen input-only classification → **EAI proprietary cognition/solvers/verification** → EAI ResultSpec → EAI-owned response rendering. Existing app.py is nonconforming and awaits migration/testing; no independent GPT-class capability has been demonstrated.

# EAI canonical architecture / ADR-0001

Date: 2026-10-31 KST. Authority: owner direction to build from minimal executable, backend-first and improve through actual use. **This document captures the final target and implementation order, not a claim that every component already exists.**

## A / B design review

A — LA-first: embed all EAI workflows and HTTP search as new LA nodes. Benefits: one workflow runtime, persistence and replay parity. Risks: existing LA intentionally disallows external connectors; changing core and HAE dependencies increases testing, blast radius and licensing/scope work.

B — EAI-first [selected]: isolated Python core, local Ollama provider, versioned tool registry, independent SQLite memory and opt-in retrieval; LA is an optional adapter after contracts/tests. Benefits: fastest stand-alone real use, protects HAE/LA and allows later reuse. Costs: some orchestration initially duplicated, interface versions to maintain. Expected performance: simpler call path for single-tool chat; costs: no paid API required; maintenance: bounded modules and tests.

## End-to-end target flow

User text → classify freshness/sensitivity/intent → local memory/cache → versioned tool/workflow registry → (optional) approved online retrieval or local solver → source parser / dedup / provenance / verification → local LLM synthesis → cited answer → local SQLite history + feedback record.

For privileged work: plan → human preview + approval → narrow tool executor or versioned LA adapter → receipt + audit + safe restart. No executable code derived directly from retrieved pages.

## Layer ownership

1. CLI (v0.1): minimal entrypoint. GUI only after backend E2E.
2. Provider port (v0.1): Ollama loopback HTTP, model swappable by name; all external cloud LLMs excluded by default.
3. Router (rule first): local chat vs freshness-sensitive online search; later ML only with measured improvement.
4. ToolRegistry (v0.1): stable tool IDs; online meta-search is web.search.v1. Later configurable skills, templates and cap-gated execution.
5. Memory (v0.1): SQLite turns, TTL cache, URL-indexed UNVERIFIED search snippets. Long-term verified knowledge and embedding/RAG are later modules, not weights training.
6. Validation (v0.1 basic): bounded inputs, loopback-only connectors, freshness warnings, source URL/time and provenance. Verified/conflict states need later independent checkers.
7. Optional integration (not implemented): Lightning Azent workflow runner behind a versioned adapter, then SOVIA/DBVORA if owner decides. HAE is a separate product.
8. Experimental future: hierarchical search/decomposition, parallel deterministic solvers, small learned route selection and evaluation benchmarks; do not confuse with LLM training.

## Existing repos verified (no code copied)

HAE main: docs/ECOSYSTEM_CANONICAL.md, Git blob 0d31062b0e3c6a570b37a35ace6fbfbe59ec2116. HAE feature/lightning-azent: packages/lightning-azent/README.md Git blob 6998c890ee6302a492d5f4b7cc825d3587ec4a16; lightning_azent/engine.py Git blob ccfbe6acdd6871b459b4eb859ba02d844989027c. The inspected LA engine supports bounded local operations and rejects unknown HTTP/network steps. Docs report isolated synthetic tests, not a production HTTP connector. Therefore do not import LA internals or pretend reusable HTTP nodes already exist.

## Failure, costs, safety

- Local Ollama absent/model not installed: fail with explicit error. Never silently switch to paid remote inference.
- SearXNG unavailable, provider blocks, or no consent: warn; use prior knowledge only as dated/unverified, never current fact.
- Search cache default 30 minutes, user may still require a fresh fetch. Store provenance and mark initial search hits UNVERIFIED.
- HTTP SearXNG endpoint must be local loopback; no automatic redirects; bounded response and short timeout. Queries sent to SearXNG may reach external public engines; owner must opt in.
- No unbounded retries; no privileged writes, shell or generalized URL fetching in initial release. Future HTTP adapter needs SSRF, redirects, DNS, size, rate-limit and permission tests.
- Schema changes and backup/restore will be versioned before additional persistent features are shipped.

## Decisions requiring new explicit approval

HAE/LA repository changes, automatic web→model fine-tuning, adding paid APIs, opening network services, autonomous workspace edits, publishing EAI, or materially changing security/data policy.
