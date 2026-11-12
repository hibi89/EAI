> **[KMONG_WORK_TARGET_GATE_20261112 | 사용자 최신 확정 | 필수 작업 규칙]** 이 저장소에서 크몽 상품·육성 후보를 작업하는 모든 AI 담당자는 새 채팅·`ㄱ` 시작 시 이 문구를 읽고 적용한다.
> - 실제 개발/수정/테스트 착수 즉시 [해총 크몽 최종완성률·후보 상태표](https://github.com/hibi89/hackathon-command-center-2026/blob/kmong-productization/docs/audits/KMONG_16_CURRENT_20261111.md)의 **해당 상품명 옆에 `**[작업중]**`을 표시하고 GitHub 커밋**한다. 확정 단계 목표(예: 95%)와 검증 기준을 제품 STATUS/HANDOFF에 남긴다.
> - **목표 완성률 달성 전에는 [작업중]을 삭제하지 않는다.** 일시중단·종료·보류·다른 제품 전환·담당 채팅 변경도 삭제 사유가 아니다. 예전 '전환·중단 시 삭제' 지시는 폐기한다.
> - **검증된 목표치에 도달한 뒤에만** 기능 SHA·PASS/FAIL/SKIP·미검증을 기록하고 자기 표시를 제거·커밋한다. 목표 하향/변경으로 표식 제거 시 사용자 명시 승인 필요. 다른 담당자 표시·기존 수치·RELEASE HOLD 보존.
> - 표식은 목표 미달 상태를 의미하며 **실시간 실행 증명은 아니다**. 허브 최신 HEAD 확인 후 안전하게 반영, 실패 시 `KMONG_HUB_SYNC_PENDING` 기록. 자동 동기화 없음. 크몽 외 작업에는 표시 불필요.

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
