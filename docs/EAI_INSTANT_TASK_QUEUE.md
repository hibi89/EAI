# EAI V3 — Instant Task Queue + Runbook + Acceptance Starter
**2026-11-17 KST** | Repo `hibi89/EAI` | Active `feature/kmong-eai-85-p31-20261112` | Baseline before blueprint: `5186cb1aa7928054d56b1cd0a40ea5943a5b3892`
**Mission lock:** EAI independent architect/player/general local AI; NOT my_local_ai coding factory; NOT Kmong packaging work unless user explicitly requests it.
**First implementation checkpoint 2026-11-17:** V3-01, V3-02, V3-11 have actual source at `b22a877e55ddab010ceb5c006e9d5016704e6366` and 19 new unit tests authored but **NOT_RUN**. Candidate status is `IMPLEMENTED_UNVERIFIED`, not verified acceptance or finished V3.1 runtime; do not infer arbitrary percent from 3/15 candidate tasks.
**Policy:** [Canonical EAI blueprint](EAI_FINAL_BLUEPRINT.md) and ADR-0002 govern. All new tasks are `DESIGNED_NOT_IMPLEMENTED`; first select READY only after HEAD reread and file/branch collision check. No invented 100%, no implied launch.

## Queue (ordered for high-throughput Instant, controlled risk)
| task_id | req_ids | depends_on | allowed_paths | acceptance | safety_checks | risk | status | evidence_sha | blockers |
|---|---|---|---|---|---|---|---|---|---|
| EAI-V3-01 | C01,C02,C28 | P0–P38 | docs/*; tests/contract*; eai/contracts.py (new) | strict v1 typed contracts, legacy compatibility fixtures, documentation crosslinks | no existing goal rewrites; no secret/data write | M | IMPLEMENTED_UNVERIFIED | b22a877e55ddab010ceb5c006e9d5016704e6366 | None |
| EAI-V3-02 | C04 | V3-01 | eai/axnode_schema.py; tests/test_axnode_schema.py; examples/axnode_synthetic/* | canonical JSON, hash, depth, duplicate-key/unsafe-op rejections | file parse only, no arbitrary exec | H | IMPLEMENTED_UNVERIFIED | b22a877e55ddab010ceb5c006e9d5016704e6366 | contract |
| EAI-V3-03 | C05,C26 | V3-02 | eai/axnode_store.py; eai/axnode_db.py; tests/test_axnode_store.py | atomic import/recovery, backup/migrate, hash parent invalidation | temp test DB, no user DB mutation | H | READY_AFTER_02 | none | schema |
| EAI-V3-04 | C06,C07 | V3-02,V3-03 | eai/axnode_retrieval.py; tests/test_axnode_retrieval.py | deterministic type/lexical/graph retrieval and negative cases | no network/index private Git content | M | READY_AFTER_03 | none | catalog |
| EAI-V3-05 | C08,C09,C19 | V3-01,V3-04 | eai/problem_model.py; eai/design_engine.py; tests/test_design_engine.py | explicit unknowns, 2 alternatives/blocked rationale, source-backed claims | no plan execution | M | READY_AFTER_04 | none | retrieval |
| EAI-V3-06 | C10,C11,C12 | V3-05 | eai/hierarchical_planner.py; tests/test_hierarchical_planner.py | bounded valid DAG/HTN; legacy 13 solver smoke and no-regression | read-only, no unbounded search | M | READY_AFTER_05 | none | design |
| EAI-V3-07 | C13,C14,C15 | V3-02,V3-06 | eai/logic_synthesis.py; eai/logic_verifier.py; tests/test_logic_synthesis.py | typed candidate composition, independent counterexample, quarantine/rollback | no executable code strings; synthetic only | H | READY_AFTER_06 | none | verifier separation |
| EAI-V3-08 | C16,C17,C18,C25 | V3-07 | eai/experience.py; eai/strategy_learner.py; tests/test_strategy_learner.py; benchmarks/eai_v3/* | heldout family split; ranker measured vs B0/B1, leak prevention | private synthetic episodes; no web training | M | READY_AFTER_07 | none | benchmark fixtures |
| EAI-V3-09 | C20,C21,C26 | V3-06,V3-07 | eai/policy_gate.py; eai/player_runtime.py; tests/test_player_runtime.py | sandbox plan hash approval, cancel/rollback, denial of unauthorized actions | explicit GO for real effects, sandbox-only first | H | BLOCKED_APPROVAL_FOR_REAL | none | owner real-action approval |
| EAI-V3-10 | C22,C23,C24,C27,C28 | V3-08,V3-09 | docs/*; eai/local_scheduler.py; eai/renderer.py; tests/* | measured offline UX/resource + optional stub adapter + R&D spec | no cross-repo writes, no GPU claims | H | PLANNED | none | earlier stages |

## Removable Hydrogen V3.1 tasks — dual mode (added 2026-11-17, DESIGN ONLY)
These REQ IDs extend the **independent EAI** V3 scope; historical P38/H01–H08 remain unchanged. No inferred implementation/verification percentage.
| task_id | req_ids | depends_on | allowed_paths | acceptance | safety_checks | risk | status | evidence_sha | blockers |
|---|---|---|---|---|---|---|---|---|---|
| EAI-V3-11 | C29,C34,C36 | V3-01 | eai/research_providers.py; eai/research_policy.py; tests/test_research_offline.py | NullProvider stable baseline; OFF network spy=0, no provider import/key; toggle & late response safe | no outbound code; no existing solver edits | M | IMPLEMENTED_UNVERIFIED | b22a877e55ddab010ceb5c006e9d5016704e6366 | shared contract |
| EAI-V3-12 | C30,C31,C35 | V3-11 | eai/hydrogen_packet.py; eai/research_quota.py; tests/test_hydrogen_policy.py | strict synthetic/public packet, per-send preview/consent, unknown paid status blocks, 429 & quota fallback mocks | NO LIVE API / BILLING / KEYS; test fake transport only | H | READY_AFTER_V3-11_MOCK_ONLY | none | live API blocked approval |
| EAI-V3-13 | C32,C33 | V3-07,V3-11,V3-12 | eai/research_candidates.py; benchmarks/eai_v3/*; tests/test_dual_mode_ablation.py | isolated model candidate cannot execute/promote, paired OFF vs mocked ON with provenance/uncertainty | no raw private prompts or automatic AXNODE promotion | H | READY_AFTER_V3-07_AND_12 | none | independent verifier |
| EAI-V3-14 | C30,C31,C33,C35 | V3-12,V3-13 | isolated optional adapter proposal; docs/*; tests/* | true Hydrogen on synthetic-only opt-in, exact account free-tier and outbound evidence, no paid fallback | live API/remote transmission needs separate user approval | H | BLOCKED_APPROVAL | none | user GO + account rate limits |
| EAI-V3-15 | C34,C36,C28 | V3-11,V3-13 | tests/*; docs/* | no-internet Windows smoke, ON failure = OFF correctness, release independent of external | actual owner Windows later, no cross-repo touch | M | READY_AFTER_V3-13 | none | device/live-model gates |
## Implementation runbook
1. On `ㄱ`: lock EAI mission, confirm exact GitHub branch/HEAD, newest `AGENTS.md` then `HANDOFF.md`, `STATUS.md`, `REQUIREMENTS.md`, [blueprint](EAI_FINAL_BLUEPRINT.md), queue and actual source. Read current task ownership, changed files and CI protection.
2. Pick 3–10 independently implementable READYs if dependencies permit; isolate H-risk or incompatible work. The first READY may need a small contract implementation without changing existing 13 CPU solvers. Never write to main or other repo without explicit instruction.
3. For each: verify allowed paths, preserve baseline, make BE/FE code changes, execute local syntax/type/minimal smoke. Run immediately necessary security/auth/data-loss/permissions checks. Do not use a docs-only commit as implementation proof.
4. Commit with authenticated identity, real changed code and tests; attach exact SHA, concise evidence. Do not fake PASS. Full CI/integration/real Windows acceptance is P2 after the actual implementation 100% candidate, except mandatory existing CI/safety gates.
5. On same-SHA verified code, update STATUS/HANDOFF and task statuses only when evidence changes; do not spam empty commits or inflate points. `IMPLEMENTED_UNVERIFIED` != acceptance. Hard blocker 2 failed unchanged approaches → quarantine and advance independent READY.
6. P2: unit/integration/contract/security/recovery/offline/windows when available; baseline B0/B1/B2 and OOD heldouts. P3 independent design/UI audit, P4 technical/security, final High review. Commercial release is separate owner approval and may remain out of scope.

## Acceptance matrix / factual checkpoints
| gate | requirement scope | baseline | current new-design state | proof needed |
|---|---|---|---|---|
| G0 | no-regression of 13 original CPU goals & P26 SHA approvals | historical Linux CI at older SHA | NOT_RUN at design HEAD | exact code SHA test suite & zero behavior drift |
| G1 | AXNODE schema/immutability/index/backup | not previously built | DESIGNED_NOT_IMPLEMENTED | golden hashes, injection/cycle/fail-closed, restore |
| G2 | architect alternatives and valid DAG | fixed old P6/P14 only | DESIGNED_NOT_IMPLEMENTED | unseen scenarios, contradictions, design trace |
| G3 | new composed logic + independent verifier | not proven | DESIGNED_NOT_IMPLEMENTED | holdout oracle, negative/proof checks, quarantine |
| G4 | experience learning/transfer | SQLite notes only | DESIGNED_NOT_IMPLEMENTED | verified episodes, family-disjoint lift vs B0/B1 |
| G5 | safe local player execution | P26 explicit read-only approval only | DESIGNED_NOT_IMPLEMENTED | sandbox receipt, rollback and privilege-denial tests |
| G6 | physical local HW/Qwen/Windows & optional adapters | real environment unverified | NOT_RUN | actual owner-approved device/model tests |
| G7 | final scope-based assessment | legacy 85% historical score | UNASSESSED | owner-approved denominator/weights & exact SHA |
| G8 | production/Kmong launch | RELEASE HOLD | HOLD | separate explicit user GO and legal/rights/ops evidence |

**NEXT READY:** V3-01 (contract + no-regression test skeleton), then V3-02 (pure AXNODE parser) in same execution only if dependencies and safety checks complete. No edits are made by this queue itself.
