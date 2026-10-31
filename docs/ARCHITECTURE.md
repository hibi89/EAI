# EAI Architecture — canonical CPU-first independent system (2026-10-31)

The owner clarification [ADR-0002](ADR-0002_EAI_COGNITIVE_OWNERSHIP.md) supersedes the old Qwen-chatbot design.

```text
User text -> CPU rule parser OR Qwen classifier (optional, INPUT only)
         -> strict IntentSpec v1 validation
         -> EAI CognitiveEngine (CPU: bounded solver, workflow/search/notes gates)
         -> ResultSpec (status/data/sources/warnings/trace)
         -> EAI ResponseEngine (deterministic, no generative LLM)
         -> local SQLite history and user note/evidence storage
```

Qwen cannot call tools or store notes: original input text must explicitly start with `기억해`/`메모추가` for a note write. Search requires explicit CLI `--online` plus a configured loopback SearXNG; its upstream may receive the query. Fetched material is UNVERIFIED, never executed as instructions.

## Decision review
A. LA-first: direct dependence on Lightning Azent workflow runtime, reuse execution but introduces coupled changes in HAE/LA and unimplemented network nodes.
B. **Independent EAI core + later optional LA adapter**: small CPU-first runtime and measured local workflows, lower integration risk, minimal startup resources. Selected for owner daily-use priority; duplicated adapter contracts are an accepted maintenance cost.

## Current runtime ports
`RuleIntentParser`, `QwenIntentParser` → `IntentSpec` → `CognitiveEngine` → `ResultSpec` → `ResponseEngine`; `Store` provides existing/history/cache/note DB operations; `WorkflowRegistry` exposes fixed `research.web.v1`. CPU_ECO sets parser `num_gpu=0`. No GPU optimization, separate original model training or full GPT-class reasoning present.

## Migration and recovery
Persistent SQLite `turns`, `search_cache`, `documents` preserved. New `user_notes` table is created additively after consistent local `<db>.pre-notes-*.bak` snapshot when opening an existing legacy DB. Backups and databases stay local and Git-ignored. Original branches/repositories untouched.

## Future
RAG/verified evidence, bounded planner/solvers, adaptive CPU/GPU scheduler (ADR-0003), LA integration, user-facing UI after backend stability. Measure success against real tasks rather than LLM-generated fluency.

## P2 extension (2026-10-31)
- `eai.analysis.compare_numeric_observations` runs Decimal-based bounded numeric ranking and input-order differences on CPU. It is independent of Ollama and LA. A zero/negative previous value disables percentage growth to prevent misleading results.
- `eai.csv_analysis.inspect_csv` reads only a user-selected local CSV path by a separate CLI subcommand. No filesystem crawls, no write capability, no network, no SQLite persistence of file rows. Read bounds: 5MiB/20k rows/32 columns/4096-char fields.
- `EAIRunner` now always uses deterministic CPU rule parsing for explicit supported command prefixes; Qwen is requested only for otherwise unsupported conversational input. This avoids GPU/model startup cost for known commands.
- Text and mixed CSV columns are not aggregated as numbers. CSV numeric means are rounded to six decimal places and explicitly labeled. This is basic descriptive analysis, not statistical inference or independent general intelligence.
