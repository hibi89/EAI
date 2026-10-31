> **Owner corrected target, 2026-10-31:** [ADR-0002](ADR-0002_EAI_COGNITIVE_OWNERSHIP.md). The existing 'Implemented Python v0.1' below describes legacy code, not compliant architecture. Planned mandatory ports: `IntentPort.parse(text)->IntentSpec` (Qwen only parse/classify), `CognitiveEngine.solve(IntentSpec)->ResultSpec` (independent EAI reasoning & decisions), `ResponseEngine.render(ResultSpec)->str` (EAI-owned deterministic output). No Qwen final synthesis. Versioned strict schemas and offline tests required prior to source migration.

# EAI interfaces — stable-contract intent

## Implemented Python v0.1

- EAI.ask(question, allow_online=False) returns Answer(text, sources, warning, cache_hit).
- OllamaChat.respond(messages) sends bounded non-streaming JSON to localhost Ollama.
- ToolRegistry.register(name, tool) / get(name) registers prebuilt tools, no per-question code generation.
- WorkflowRegistry.execute("research.web.v1", registry, query, allow_online=True) executes a fixed consent-gated template; no generated nodes, shell or external writes.
- SearxNGSearch.search(query, limit<=8) reads an explicitly configured localhost JSON API and returns SearchHit(title,url,snippet).
- Store.add_turn / recent_turns / read_search_cache / save_search / recall own local SQLite rows. External source results start UNVERIFIED.

## Planned typed contract, not yet runnable

ToolSpec eai.tool.v1: id, version, input_schema, output_schema, effects (read/local-write/external-write), required_permissions, timeout_ms, quota, cache_policy, implementation_id, provenance.

WorkflowSpec eai.workflow.v1: workflow_id, version, ordered/parallel bounded steps, references to registered tool IDs, typed parameters, per-step effect policy, error fallback, receipt and output schema.

Runtime: EAI router selects **existing** workflow IDs with validated parameters, never synthesizes unrestricted Python from the user prompt. A template can be composed from known tools and saved only after user preview if it changes behavior. Future LA integration maps to supported azent.ir.* and rejects unsupported nodes rather than executing with fabricated parity.

## Source evidence status

UNVERIFIED = fetched snippet only; VERIFIED = reproducible independent source/checker evidence (future); CONFLICT = verified contradiction; UNAVAILABLE = insufficient or failed retrieval. Do not mark search hits VERIFIED by LLM confidence alone.

## Data authority

Conversation, cache, and local knowledge stay on the user's PC. Model files installed separately. Large raw datasets must not enter GitHub. Sensitive user text must not be included in external search queries without explicit approval.
