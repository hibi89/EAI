> **2026-11-10 P15 new user-facing bounded skill verified:** Stdout-only `make-manifest` generates batch/pipeline schema v1 with exact SHA256 for 1–6 named local goal docs, preflight directory restrictions, duplicate/cycle/symlink/extra command rejection; never executes a goal or writes/contacts remote. Source SHA `c35269299f0cdfaa42c51eb8351db50b9e7ec93d` [GitHub Actions #42676269100](https://github.com/hibi89/EAI/actions/runs/42676269100) Linux Python3.11 **320/320 PASS / 0 FAIL**, compileall/CLI smoke PASS (P15 +19). Whole-product estimated **41%** (+1%p from verified 40); real Windows, installed Qwen/Ollama, customer product workflows and release permission still unverified. Existing P0–P14 contracts preserved, main unchanged.

> **2026-11-10 latest P13/P14 delivered and verified**: `doctor` (8 offline probes including strict synthetic status, goal pipeline, in-memory SQLite), `pipeline-goals` (typed 1-6 node DAG with dependency gate, file SHA256 source integrity, independent order and postcondition). Code/test SHA **`bbd01576eed2573ffeab5a70eec0662fcb40bad0`** [GitHub Actions #42675220982](https://github.com/hibi89/EAI/actions/runs/42675220982) **Linux Python3.11 301/301 PASS / 0 FAIL, CLI smoke and compileall PASS**. Previous P13/P14 CI pre-job failure and an intermediate 2-test naming error are historical, resolved evidence. Product-wide provisional completion **40%** (+2%p from 38%), not GPT-class intelligence. Real Windows 10/11, Qwen/Ollama local parser, search, customer tasks, product packaging, retail license and deployment are still unverified and release HOLD.

> **2026-11-10 최신 요구/검증 분리:** P12 `batch-goals` 최대6 로컬 목표 SHA256·중복/경로 차단·에러 격리 및 검증 receipts 도입, [기능 소스 SHA d5f928... GitHub Python3.11 269 PASS](https://github.com/hibi89/EAI/actions/runs/42670939944). P13 `doctor`(현재 소스 12 test methods), P14 `pipeline-goals`(15 test methods) 기능 소스가 존재하지만 [P13 CI](https://github.com/hibi89/EAI/actions/runs/42671534452) 및 [P14 CI](https://github.com/hibi89/EAI/actions/runs/42672478578)가 Job 생성 전 FAILURE로 최신소스 전체 검증 **미완**. 현재 전체 상품 완성률 38% 유지, 39/40% 및 50% 달성 주장 금지. Windows/Qwen/상용 배포 HOLD.

> **P11 added/verified 2026-11-10:** strict CPU `schedule_tasks` fourth goal domain (DAG critical-path CPM, minimum finish, latest/earliest/slack, deadline gate, bounded 24 tasks and independent verified receipt), no automatic work execution. P10/P11 extreme fixed-point Decimal precision hardened to 90. Exact feature/test SHA `42d6b53400fd841d6f5f4e3db0e97583bf3996cd`, [Actions #42666810963](https://github.com/hibi89/EAI/actions/runs/42666810963) 249/249 Python3.11 Linux PASS, compileall/CLI smoke PASS. Completion estimate **37% (+1%p)** based on actual new functionality, not generalized intelligence or product release; Windows/customer/offline local Qwen/Ollama still unverified. Preserve P0-P10 and main.

> **2026-11-10 P10 3rd goal skill implemented / final product estimate 36%:** 정확 리소스 제약 task portfolio `plan_tasks` (12개 작업·선행조건·양의 가치 조합·동점 보류·독립 검증). 코드 SHA `843a1426ac4c2dcb4c0e957768bc94ea04078f02` [Linux Python3.11 Actions 229/229 PASS](https://github.com/hibi89/EAI/actions/runs/42664669185); 외부 API 없음. 기존 35%에 실기능 1%p 잠정 증가. Windows, 실제 고객 사용, 일반 AI 역량, 판매권/출시 조건은 미검증. 기존 P0–P9 계약 보존.

> **2026-11-10 P9 delivered with exact-code CI:** P8의 선택지 영수증 검증에 독립적인 표시 근거 재계산(`eai/receipt_evidence.py`) 및 10개 신규 회귀를 추가했다. 검증 소스 SHA `da48d1764f8a369905ef34bd6810cb738efb8a2b`, GitHub Actions [#42659433939](https://github.com/hibi89/EAI/actions/runs/42659433939) Linux Python3.11 **211/211 PASS, compileall/CLI smoke PASS**. 제품 최종상용화/실 Windows/LLM 검증은 별도이며 범용 GPT 수준 미달. 기존 P8 201건 상태와 CI pre-step failure는 과거 이력으로 보존.

# EAI REQUIREMENTS — P8, 2026-10-31 KST

## Goal and boundary
Independent EAI for local daily use: optional Qwen strictly parses/classifies user INPUT. EAI-owned CPU code plans bounded tasks, computes, selects, validates and renders outputs. GPT-level all-domain cognition, original language model training and universal agent capability remain unproven future research.

## Implemented
- P0: strict intent, local CPU arithmetic, optional opt-in localhost search, SQLite history/cache.
- P1: explicitly authorized local notes, recall, and pre-migration SQLite backup.
- P2: Decimal comparison and bounded read-only CSV profile.
- P3: claim-vs-CSV numerical verification and hash-backed result.
- P4: keyed two-file reconciliation and evidence checks.
- P5: multi-metric discrepancy diagnosis with bounded candidate hypotheses, not causal attribution.
- P6: fixed goal planner for CSV audit, read-only fallback/escalation, hash verification.
- P7: two strict local JSON goal kinds, choose_options (weighted score, hard limits, Pareto) and csv_audit.
- P8: independent receipt guard rechecks original constraints, scoring, Pareto winners, CSV file hashes, route strategy, status and allowlisted steps; returns bounded advisory details, fails closed on forged/inconsistent receipts.

## Nonfunctional requirements
Python >=3.11 standard library, CPU-first, no paid API/GPU required for deterministic tasks, user-private files never uploaded, no unapproved file modifications, no default listener, no arbitrary code execution or self-changing goal constraints. Only explicit --online search may relay queries through local SearXNG. No HAE/LA/main changes. New billing, permissions, model training, sensitive external transfer, autonomous writes or public deployment require owner approval.

## Gates
Linux Python 3.13.5 local mirror: 201 PASS, 0 FAIL, including 21 P8. Three P8 blobs exactly match GitHub; full byte-identical checkout tests are not proven. GitHub Actions runner pre-step failure persists, real Windows Python 3.11 and Ollama/SearXNG unverified; no Vercel Production target.
