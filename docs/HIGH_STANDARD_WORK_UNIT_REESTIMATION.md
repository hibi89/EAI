> **[OWNER-SWU-P1-ONLY-UNIVERSAL · 2026-11-17 KST]** 이번 재산정은 각 제품만의 임시 최적화가 아니라 **향후 모든 프로젝트에 공통 적용되는 P1 구현단위(SWU)**의 첫 적용이다. **웹 GPT-6 Sol High 1회의 실제 코딩으로 기능 경로가 연결될 수 있는 크기**를 정한다. 브라우저/전체 CI/보안 종합검수/통합/E2E/회귀/실기기 등은 **P2 검증완료율 큐**이므로 SWU 크기·시도횟수·P1 구현완료 조건에서 **제외**한다. P1의 필수 syntax/type/minimal smoke, 인증·권한/비밀/원본·데이터손실·F18 즉시 위험검사 및 기존 필수 CI·GO는 그대로 적용. 1회 완성 목표/일반 최대2회/High 특수 최대3회와 ㄱ당 독립 4~6 SWU는 **P1 코딩 작업에만** 적용되며 P2 작업단위/반복횟수의 한도로 사용하지 않는다.

# EAI V3.1 — 웹 GPT-6 Sol High 기준 P1 작업단위 전수 재산정 지시 (2026-11-17 KST)

**WORK ORDER:** EAI-SWU-HIGH-REESTIMATE-20261117
**대상:** `hibi89/EAI@feature/kmong-eai-85-p31-20261112`
**담당:** EAI V3.1 최종설계/작업계획 담당 웹 GPT-6 Sol High. Instant 담당자는 승인된 SWU 큐를 실행.
**현행 작업 구성:** **V3 구현 작업군 15개**, 실제 REQ 범위·완료 상태는 현재 `docs/EAI_FINAL_BLUEPRINT.md`와 `docs/EAI_INSTANT_TASK_QUEUE.md` 정본에 따름. MLA의 30 REQ/28 task 숫자를 복사하지 말 것.
**임무:** 기존 15개 작업군이 High 1회에 완료 가능한 **실제 수직 기능**인지 전체 점검하고 분할·병합·재산정. 단순 '1~3회 제한'이나 4~6개 READY 표시는 산정 완료가 아니다.

## 표준 기준과 즉시 실행 순서
- [해총 OWNER-SWU-HIGH-20261117 표준작업단위 정본](https://github.com/hibi89/hackathon-command-center-2026/blob/kmong-productization/docs/strategy/GPT6_HIGH_STANDARD_WORK_UNIT_20261117.md)이 이번 **작업 분해/크기** 판단에 우선한다. **기준 모델은 웹 GPT-6 Sol High**. `1 SWU`는 High 작업 회차 한 번의 의미 있는 코딩 시도로 **실제 호출자→모듈→상태/출력까지 구현 코드 완성 후보**를 만들 수 있는 1개의 독립 수직 기능. Instant/개별 GitHub API 호출/LOC 수/REQ 개수 기준으로 분해 금지.
- 점수 축 5개 `S(표면), C(계약), I(통합), D(데이터/보안), U(불확실성)`, 각각 0/1/2점. **0–3 표준 1회 목표**, 4–5 우선 분할 또는 근거 있는 High 원자적 예외, 6–10 반드시 High 재분할/고위험 분리(불가피한 경우 사전 High 판단·사용자 승인 아래 3회 예외). D=2/U=2는 점수와 무관하게 위험 검토. 고위험/미승인 실행을 소스 코딩 큐와 섞어 READY로 해제 금지.
- 1 SWU마다 일반 **1회**, 수정 허용 **최대 2회**, 승인된 원자적 고난도 **최대 3회**. `ㄱ` 횟수·CI polling·조회·문서 커밋이 아니라 **실제 기능 소스 구현 회차**를 누적. 같은 원인으로 진전 없는 실패 2회면 즉시 해당 SWU HOLD/High 이관·독립 READY 계속. 모바일 `ㄱ`당 충돌 없는 SWU 4~6개 묶음 시도를 **목표**로만 사용.
- 실제 코드/REQ 경로를 감사하고 `Preview/Intent`, 합성 테스트, 문서·evidence SHA만 있는 단위를 **구현완료로 인정하지 않는다**. 이미 기능 소스 경로가 완성된 것은 별도 표시해 재구현하지 않는다. P1 코드/국소 검사와 P2 실브라우저/전체 CI/실기기 검증, 실운용/외부전송/권한 GO를 구분한다.
- 기존 REQ-ID·확정 설계·원본 안전 제한·브랜치·Git 이력·검증 큐·P2 LOCK을 변경하지 않는다. 작업 수는 **산정 결과**이지 목표값이 아니다. **현재 단계는 재산정**, 구현률 변경 0.

## 산출 요구사항
기존 `legacy_task_id` 전항목을 아래 구조로 전수 매핑하고, 이미 충족된 코드와 실제 미구현 호출경로를 가려 새 SWU 분할·병합안을 제시한다.

```text
legacy_task_id | req_ids | existing_source_paths | caller_to_callee | unimplemented_function |
S,C,I,D,U,total_score | proposed_swu_id | observable_outcome |
code_depends_on | runtime_security_dependencies | allowed_paths |
p1_source_acceptance | p2_deferred_tests | task_attempts (inherited) |
max_attempts | status | evidence_sha | blockers
```

**완료 조건:** (1) 기존 작업/REQ 매핑 누락·중복 0, (2) 각 SWU 관찰 가능한 실제 기능 1개/합리적 크기 점수·근거, (3) 기존 시도·SHA·실패·권리/신뢰 경계 보존, (4) 변경 전후 항목 수·점수 분포·원인별 분할/병합 목록, (5) 첫 독립 READY 4~6개 및 왜 단일 High 회차 내 코드 완성 후보가 가능한지 설명, (6) 위험한 코딩·실운용 게이트 별도 유지, (7) 원격 HEAD/반영 SHA·검증 사실/미실시 구분.

단순 정책 문서 기록으로 완료를 선언할 수 없다. 실제 최종설계/요구사항/소스 전수를 읽고 **기존 정본 큐와 연결된 재산정안**을 확정해야 한다. 재산정 결과로 작업 카운트를 조정할 때는 이전 인수인계/구현 SHA·시도 횟수를 승계하고 기존 큐의 고유 안전 상태와 검증 잠금 필드를 보존한다. 사용자 승인 최종설계는 변경하지 않는다.

## EAI 특별 보존 및 통합 지시
1. `docs/EAI_FINAL_BLUEPRINT.md`, `docs/EAI_INSTANT_TASK_QUEUE.md`, `REQUIREMENTS.md`, 실제 `eai/`·`tests/`, AGENTS/HANDOFF/STATUS를 **기능별 source caller→callee**로 교차 감사한다. 단순 CPU 프리뷰·보안 반복 수정보다 **Architect→Player→AXNODE·Experience Learner**가 자기 책임의 실제 로컬 실행 경로로 연결되는 미구현 간극을 기준으로 분리한다.
2. 기존 15 작업군의 각 `req_ids` 또는 최종설계 C/기능 ID를 새 SWU에 모두 연결한다. 현재까지 실제 코드 후보 3/15, 나머지 부분 구현/승인 차단 등의 오래된 기록은 최신 HEAD와 검증해야 한다. **15개의 그룹 개수를 목표로 유지하거나 MLA 방식에 맞춰 28/30으로 변경하지 않는다.**
3. **EAI의 독립 목표**는 My Local AI의 코딩 실행기가 아니다. EAI Architect/Player/AXNODE 설계, 구 CPU 13개 범주, ADR-0002/Qwen INPUT-only, 선택형 Hydrogen 기본 OFF/외부 전송 무승인, 실제 ACTIVE/실도구/독립 승인/고객 DB 보호를 그대로 둔다. Source 작성과 ACTIVE 권한은 완전히 별도다.
4. 현재 `docs/EAI_INSTANT_TASK_QUEUE.md`의 역사적 장문 이력은 보존하면서 본 파일의 mapping을 재산정 정본으로 연결하고, 중복되는 작업 정책의 3~5 READY 같은 옛 배치 숫자는 최신 **High 1회 SWU 기준 4~6**에 밀려난다는 것을 명확히 한다. 소스-only/미검증을 VERIFIED로 바꾸지 않는다.
5. 최종설계 무변경 원칙을 지키며 새 SWU 목록/의존성·권한·수용조건을 현행 큐/Runbook에 반영해 후속 개발자가 다음 `ㄱ`에 즉시 코딩할 수 있어야 한다.

**다음 EAI `ㄱ` 실행 첫 단계:** 이 재산정 대응표와 High 1회 구현 용량 검사 → 정합성 확인 후 첫 READY 4~6개 실제 미완성 기능 코드 구현. 단순 상태 공지만 반복하지 않는다.
