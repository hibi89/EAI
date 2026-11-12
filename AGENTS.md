> **[OWNER-FINAL-BLUEPRINT-100 | 2026-11-13 KST | 사용자 확정]** 공식 최종완성률은 **사용자 최종설계도 전체 = 100%** 기준으로만 산정. 작업자·총괄이 임의 설계 범위·가중치·수용조건 축소/수정 금지. 해커톤 MVP, 합성/CI, P85/P95 같은 기술 마일스톤을 공식 최종완성률로 부르면 안 된다. 최종설계 요구 ID→소스→정확 SHA 검증·미검증→승인 가중치 100점 추적표와 대조. 근거가 없으면 공식 `UNASSESSED(재산정 대기)`; 과거 수치는 내부 역사 지표로 보존. 해총 `kmong-productization` 최종완성률 원장에 결과 동기화. 기존 [작업중]/등록이력·RELEASE HOLD 변경 금지. [공통 정본](https://github.com/hibi89/hackathon-command-center-2026/blob/kmong-productization/docs/strategy/FINAL_BLUEPRINT_COMPLETION_STANDARD_20261113.md). 정책 커밋은 기능 완료나 점수 확정이 아니다.

# AGENTS — EAI chief directive

Read `HANDOFF.md` → `STATUS.md` → `AGENTS.md` → `REQUIREMENTS.md` → actual source each new chat.

## Canonical goal
[ADR-0002](docs/ADR-0002_EAI_COGNITIVE_OWNERSHIP.md) controls: optional local Qwen parses/classifies **INPUT ONLY**. Independent EAI CPU cognition owns solution planning, tool selection, validation, memory and final deterministic rendering. Do not silently return to a Qwen-generated chatbot or claim GPT-class intelligence. [ADR-0003](docs/ADR-0003_ADAPTIVE_CPU_GPU_RESEARCH.md) is hardware optimization research, not measured results.

## Development agreement
- User owns private `hibi89/EAI` GitHub as source of truth. Existing main branch and HAE/LA/other project source/data preserved. Work minimally on `feature/local-first-mvp`.
- Owner's main priority: **actually usable EAI**, starting from CLI and progressively widening proven independent tasks. Design UI last.
- Compare at least two approaches before significant architecture, external transfer, permissions, data overwrite, paid services, training or original source changes; owner approval where required.
- Test exact source when possible, separately report mocked unit PASS vs real Ollama/Windows/browser/CI. Do not infer CI success from empty statuses; GitHub Actions runs currently show failure.
- User types `ㄱ` to continue next safe task. After substantive changes update STATUS/HANDOFF with timestamp, current SHA, reproducible tests, blockers and next steps.
- No secrets, .env, local databases, backup snapshots, model weights or personal prompts in GitHub. No silent cloud LLM calls or external prompt upload.
- Every new skill/workflow is versioned, bounded, permission-gated, reversible. Qwen classification may never authorize privileged writes by itself.
- Existing LA/HAE is optional peer, not dependency. No LA repo changes without approval.
- Stop and pivot when two retries of the same path yield no verified progress; never force push.
