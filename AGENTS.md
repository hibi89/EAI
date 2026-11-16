> **[OWNER-DEV-EXECUTION-V2 | ACTIVE]** [2026-11-16 사용자 확정 최신 실행·복원 정본](https://github.com/hibi89/hackathon-command-center-2026/blob/kmong-productization/docs/strategy/OWNER_DEV_EXECUTION_CANONICAL_20261116.md): **웹 GPT-6 Sol High 최초 전체 설계/Instant 작업큐 → 웹 GPT-6 Sol Instant BE/FE 구현 후보100%까지 묶음 코딩 → 최종 전체 CI·수정(고위험 최소검사 즉시) → Codex GPT-6.1 Sol Max 기술·Astra Max 디자인 독립검수 → 웹 Sol High 최종 인수 → 형 승인 후 Codex Luna Extra High 크몽 등록.** 구형 '4개 작업슬롯만', High 단독 코딩, 매 작업 전체 CI, 중간 검수·디자인 순서는 효력상 대체; 최종설계·보안/원본/외부비용/법적권리/상품 HOLD는 유지. 이 정책 기록 자체는 제품 재개·CI·출시 허가가 아니다. **새 채팅은 역할/브랜치 HEAD와 최신 AGENTS를 우선 확인하고 HANDOFF→STATUS→REQUIREMENTS→최종설계→실코드·큐 순으로 대조**한다. HANDOFF 오래된 지시가 정책을 덮어쓰지 못하며 `ㄱ`은 해당 제품만 재개한다. 구현률/공식 검증률 구분, 허위 1%p 금지.

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
