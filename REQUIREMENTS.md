> **P5 scope (2026-10-31):** Add CPU-owned `diagnose-csv` multi-metric discrepancy and candidate-cause tracing for 1–8 numeric columns across two user-selected CSVs, with P4 data validation, SHA-256 checks and bounded, explicitly sample-limited candidates. Qwen never judges evidence. Candidate hypotheses may not assign source truth. Tests: 122 local PASS, remote Actions FAILURE, Windows UNVERIFIED. [P5 contract](docs/P5_MULTI_METRIC_DIAGNOSIS.md).

> **P4 추가 요구사항 (2026-10-31):** 명시적으로 선택한 서로 다른 로컬 CSV 두 개의 공통 고유 키별 숫자를 CPU에서 비교한다. 개별 값·키 누락·비숫자·중복 키·원본 해시를 검사하고 AGREE/CONFLICT/UNAVAILABLE를 분리한다. 합계 동일이 개별 일치를 의미하지 않는다. Qwen과 유료 API를 사용하지 않으며 외부 전송·원본 수정은 금지한다. 기존 P0~P3 기능을 보존한다. 세부 계약: [P4 교차검증](docs/P4_KEYED_CSV_RECONCILIATION.md). **로컬 회귀 테스트 97 PASS / 원격 CI 실패 / Windows 실기기 미검증.**

> **P2 implementation scope, 2026-10-31:** Add CPU-owned exact numeric pair comparison (rank, max/min, difference, sequential absolute/percentage change) plus a strictly opt-in read-only local CSV profiler (rows/columns/missingness/sums/min/max/mean). Existing Qwen remains optional input classification only; no model may synthesize final answers. No cloud data transfer or autonomous file reads. Full acceptance and known limits: [P2_CPU_ANALYSIS](docs/P2_CPU_ANALYSIS.md).

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
