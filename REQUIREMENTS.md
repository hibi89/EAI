# REQUIREMENTS — EAI local-first independent engine

## Vision
Elice Artificial Intelligence (EAI) is an independently authored, CPU-first personal agent intended for iterative expansion over 6–12+ months. Its long-term aspiration is strong general task-solving; this is **unproven research**, not a current GPT-equivalent model. Qwen/Ollama are optional **input interpreters only**; results and decisions belong to EAI-owned code.

## Functional P1 acceptance (implemented local)
- Strict IntentSpec v1 and deterministic CPU rule parser fallback, no model-authored final answer.
- CPU bounded exact Fraction/Decimal arithmetic, unsupported-task warnings.
- Versioned consent-gated local SearXNG search with cached unverified snippets and remote lookup OFF by default.
- Local SQLite history plus explicit user notes: `기억해`, `메모추가`, `메모목록`, `기억검색`; note write demands literal user command regardless of Qwen output; note insert idempotent.
- Before adding notes schema to existing DB, transactionally consistent local SQLite backup, no delete/overwrite of original rows.
- Python 3.11+ stdlib, no paid API, no GPU or model dependency for core CPU-rule tasks. Real hardware Qwen and Windows tests remain separate acceptance gates.

## Engineering and privacy constraints
No network listener by default, no unsigned model downloads, no unapproved paid services or external sensitive data transfer; localhost source access only where configured. New modules preserve data, test restart recovery, validate bounded inputs, separate note content and unverified web evidence, keep private DB/snapshots out of Git. No autonomous file edits or command execution. The launcher and real local model/search services must be verified on actual PC before release claims.

## Future milestones (not present)
Document/semantic RAG, larger reasoning solver library, LA adapter as optional versioned port, hierarchical search, CPU/GPU scheduler after hardware benchmarks, learning route selection with held-out tests, and eventual native GUI. Implement based on real use cases, not speculative showcase.
