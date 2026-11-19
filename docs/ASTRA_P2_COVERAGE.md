# Astra review evidence by requirement

Windows self-test at candidate commit `3f5efeb810aa0675476f551913d3b6a8d5f7b591`. P and S count distinct passing and skipped methods within a named suite. Suites recur across contracts. Only the 1,110 unique cases in the machine-readable test list form a total. Each row associates the canonical scope with actual execution. Whole-requirement acceptance and weighting are UNASSESSED. A method executed against a mock establishes the local contract only.

## Backend work units

| SWU | REQ | Canonical contract | Executed suites | Astra result |
|---|---|---|---|---|
| EAI-SWU-001 | C01, C02 | Typed ProblemSpec JSON -> digest | [contracts_v3](../tests/test_contracts_v3.py) 7P | PASS scoped local suites |
| EAI-SWU-002 | C02, C28 | Architect decision -> typed final ResultSpec | [contracts_v3](../tests/test_contracts_v3.py) 7P, [decision_engine](../tests/test_decision_engine.py) 18P | PASS scoped local suites |
| EAI-SWU-003 | C03 | Optional Qwen INPUT -> CPU problem fallback | [core](../tests/test_core.py) 18P, [local_qwen_acceptance_p36](../tests/test_local_qwen_acceptance_p36.py) 8P, [architect_runtime](../tests/test_architect_runtime.py) 8P | PASS scoped local suites. Optional P36 gate BLOCKED |
| EAI-SWU-004 | C04 | Node JSON -> immutable AXNODE SHA | [axnode_schema](../tests/test_axnode_schema.py) 8P | PASS scoped local suites |
| EAI-SWU-005 | C05 | AXNODE import -> catalog -> reload receipt | [axnode_store](../tests/test_axnode_store.py) 6P/1S, [axnode_maintenance](../tests/test_axnode_maintenance.py) 5P | PASS scoped local suites |
| EAI-SWU-006 | C05, C26 | Owned sidecar -> staged backup/isolated restore | [axnode_sidecar_backup](../tests/test_axnode_sidecar_backup.py) 11P, [axnode_recovery](../tests/test_axnode_recovery.py) 4P/1S | PASS scoped local suites |
| EAI-SWU-007 | C05, C26 | Sidecars -> cross-DB coherent epoch | [sidecar_coherence_review](../tests/test_sidecar_coherence_review.py) 13P, [sidecar_recovery_audit](../tests/test_sidecar_recovery_audit.py) 9P/1S | PASS scoped local suites |
| EAI-SWU-008 | C05, C26 | Staged restore -> isolated commit/rollback | [axnode_isolated_restore](../tests/test_axnode_isolated_restore.py) 13P | PASS scoped local suites |
| EAI-SWU-009 | C06 | Architect query -> typed AXNODE retrieval | [axnode_retrieval](../tests/test_axnode_retrieval.py) 6P | PASS scoped local suites |
| EAI-SWU-010 | C07 | Local experience -> five-tier memory | [axnode_memory](../tests/test_axnode_memory.py) 5P, [episode_replay](../tests/test_episode_replay.py) 7P | PASS scoped local suites |
| EAI-SWU-011 | C06, C07 | Withdrawn parents -> negative result filter | [axnode_memory_review](../tests/test_axnode_memory_review.py) 6P | PASS scoped local suites |
| EAI-SWU-012 | C08 | ProblemSpec -> constraints/UNKNOWN | [architect_runtime](../tests/test_architect_runtime.py) 8P, [contracts_v3](../tests/test_contracts_v3.py) 7P | PASS scoped local suites |
| EAI-SWU-013 | C09 | ProblemModeler -> 2 designs/abstain | [design_engine](../tests/test_design_engine.py) 10P | PASS scoped local suites |
| EAI-SWU-014 | C19 | Local claim -> evidence ledger -> Architect uncertainty | [evidence_architect](../tests/test_evidence_architect.py) 5P, [architect_runtime](../tests/test_architect_runtime.py) 8P | PASS scoped local suites |
| EAI-SWU-015 | C10 | Design -> hierarchical bounded PlanSpec | [hierarchical_planner](../tests/test_hierarchical_planner.py) 11P | PASS scoped local suites |
| EAI-SWU-016 | C11 | Candidate DAGs -> CPU cost rank | [hierarchical_planner](../tests/test_hierarchical_planner.py) 11P, [design_engine](../tests/test_design_engine.py) 10P | PASS scoped local suites |
| EAI-SWU-017 | C12 | Typed DAG -> 13 legacy skills read-only | [goal_dispatch](../tests/test_goal_dispatch.py) 16P, [goal_pipeline_p14](../tests/test_goal_pipeline_p14.py) 18P | PASS scoped local suites |
| EAI-SWU-018 | C13 | Pinned nodes -> bounded typed synthesis | [logic_synthesis](../tests/test_logic_synthesis.py) 11P | PASS scoped local suites |
| EAI-SWU-019 | C14 | Counterexample -> bounded synthesis revision | [logic_counterexamples](../tests/test_logic_counterexamples.py) 4P, [logic_oracle](../tests/test_logic_oracle.py) 7P | PASS scoped local suites |
| EAI-SWU-020 | C14, C15 | Independent receipt -> candidate review | [candidate_evidence_review](../tests/test_candidate_evidence_review.py) 10P, [candidate_review_journal](../tests/test_candidate_review_journal.py) 15P/1S | PASS scoped local suites |
| EAI-SWU-021 | C15 | Reviewed node -> quarantine/activation intent | [candidate_activation_preflight](../tests/test_candidate_activation_preflight.py) 4P | PASS scoped local suites |
| EAI-SWU-022 | C16 | Owned Player observation -> replayable episode | [episode_replay](../tests/test_episode_replay.py) 7P, [episode_replay_dedup](../tests/test_episode_replay_dedup.py) 7P | PASS scoped local suites |
| EAI-SWU-023 | C16, C17 | Independent episode SHA -> experience gate | [experience_admission](../tests/test_experience_admission.py) 12P, [episode_replay_fence](../tests/test_episode_replay_fence.py) 6P/1S | PASS scoped local suites |
| EAI-SWU-024 | C17 | Verified outcomes -> local StrategyLearner | [verified_learning_boundary](../tests/test_verified_learning_boundary.py) 18P, [strategy_research_ranker](../tests/test_strategy_research_ranker.py) 8P | PASS scoped local suites |
| EAI-SWU-025 | C18 | Synthetic curriculum -> gap-driven next case | [synthetic_curriculum](../tests/test_synthetic_curriculum.py) 5P, [synthetic_holdout](../tests/test_synthetic_holdout.py) 10P | PASS scoped local suites |
| EAI-SWU-026 | C25 | Local cost results -> strategy ranker state | [strategy_research_ranker](../tests/test_strategy_research_ranker.py) 8P, [synthetic_candidate_benchmark](../tests/test_synthetic_candidate_benchmark.py) 8P | PASS scoped local suites |
| EAI-SWU-027 | C20 | Problem/Plan -> pure PolicyGate HOLD | [policy_gate_player](../tests/test_policy_gate_player.py) 11P | PASS scoped local suites |
| EAI-SWU-028 | C21 | Pure plan -> synthetic Player trace | [policy_gate_player](../tests/test_policy_gate_player.py) 11P, [player_cli](../tests/test_player_cli.py) 5P | PASS scoped local suites |
| EAI-SWU-029 | C21, C26 | Scoped action -> isolated Player operator port | [policy_gate_player](../tests/test_policy_gate_player.py) 11P, [synthetic_candidate_execution](../tests/test_synthetic_candidate_execution.py) 12P | PASS scoped local suites |
| EAI-SWU-030 | C21, C26 | Observed sandbox result -> compensation | [policy_gate_player](../tests/test_policy_gate_player.py) 11P, [episode_replay](../tests/test_episode_replay.py) 7P | PASS scoped local suites |
| EAI-SWU-031 | C22 | Adapter handshake -> local OFF port registry | [adapter_stub](../tests/test_adapter_stub.py) 7P | PASS scoped local suites |
| EAI-SWU-032 | C23 | CPU process RSS -> bounded scheduler decision | [local_scheduler](../tests/test_local_scheduler.py) 11P, [offline_journey](../tests/test_offline_journey.py) 31P | PASS scoped local suites |
| EAI-SWU-033 | C24, C27, C28 | Decision -> redacted trace and research separation | [trace_renderer](../tests/test_trace_renderer.py) 13P, [decision_engine](../tests/test_decision_engine.py) 18P | PASS scoped local suites |
| EAI-SWU-034 | C29, C34, C36 | OFF policy -> NullProvider -> same baseline | [research_offline](../tests/test_research_offline.py) 5P | PASS scoped local suites |
| EAI-SWU-035 | C30, C35 | Synthetic ResearchPacket -> owner consent fence | [hydrogen_policy](../tests/test_hydrogen_policy.py) 5P, [research_offline](../tests/test_research_offline.py) 5P | PASS scoped local suites |
| EAI-SWU-036 | C31 | Local research quota -> durable breaker | [hydrogen_policy](../tests/test_hydrogen_policy.py) 5P, [research_mock_transport](../tests/test_research_mock_transport.py) 6P | PASS scoped local suites |
| EAI-SWU-037 | C32 | Untrusted mock idea -> quarantined metadata | [research_candidates](../tests/test_research_candidates.py) 9P | PASS scoped local suites |
| EAI-SWU-038 | C33 | OFF plus mock ON -> attributed comparison result | [dual_mode_ablation](../tests/test_dual_mode_ablation.py) 6P, [research_mock_transport](../tests/test_research_mock_transport.py) 6P | PASS scoped local suites |
| EAI-SWU-039 | C30, C35 | Owner consented public packet -> live Hydrogen candidate | [hydrogen_live_http](../tests/test_hydrogen_live_http.py) 10P, [hydrogen_policy](../tests/test_hydrogen_policy.py) 5P | PASS scoped local suites. Live provider BLOCKED_APPROVAL |
| EAI-SWU-040 | C31, C33 | Late/429 research reply -> OFF result | [research_mock_transport](../tests/test_research_mock_transport.py) 6P, [research_offline](../tests/test_research_offline.py) 5P | PASS scoped local suites |
| EAI-SWU-041 | C34, C36 | Local goal -> Architect/Policy/Player -> decision | [offline_journey](../tests/test_offline_journey.py) 31P, [decision_engine](../tests/test_decision_engine.py) 18P | PASS scoped local suites |
| EAI-SWU-042 | C28, C36 | EAI CLI goal -> independent CPU answer | [eai_preview_cli](../tests/test_eai_preview_cli.py) 8P, [trace_renderer](../tests/test_trace_renderer.py) 13P | PASS scoped local suites |

## Desktop work units

| SWU | REQ | Canonical contract | Executed evidence |
|---|---|---|---|
| EAI-FE-001 | EAI-FE-C01 | Native dark desktop shell with persistent natural-language composer and navigation | PASS · 7 pages, six client layouts, permanent composer and keyboard |
| EAI-FE-002 | EAI-FE-C02 | Literal rule intent -> existing CPU EAI answer and explicit note consent | PASS · Real CPU result 84, note consent, holds and no transcript writes |
| EAI-FE-003 | EAI-FE-C03 | Local goal draft editor -> validated new ProblemSpec -> Architect CPU preview | PASS · Validated structured/raw editor, 2 plans, save/reopen/error cases |
| EAI-FE-004 | EAI-FE-C04 | AXNODE read-only graph, local metadata and provenance | PASS · 3-node graph + parent/digest, live WAL, 243-node bounded search |
| EAI-FE-005 | EAI-FE-C05 | Verifier and Player no-op simulator, consent and review gating | PASS · Changed-plan refusal, two pure steps, receipt conflict and unknown counts |
| EAI-FE-006 | EAI-FE-C06 | Native EXE entrypoint and reproducible Windows unsigned candidate packaging | PASS · Standalone EXE opened/closed twice on host and twice in offline Windows Sandbox |

[Interaction-level tests and reproduction](ASTRA_WINDOWS_HANDOFF.md#desktop-interactions)

## Blueprint C01–C36

| REQ | Area | Blueprint acceptance target | SWUs above | Evidence boundary |
|---|---|---|---|---|
| C01 | EAI vs my_local_ai scope & trust boundary | Neither backend can impersonate the other; no cross-repo edits | 001 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C02 | Versioned ProblemSpec/DesignSpec/PlanSpec/ResultSpec | schema round-trip, invalid/unknown fields fail closed | 001, 002 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C03 | Qwen INPUT-only; CPU fallback | spy tests prove no final Qwen answer/tool authority | 003 | CPU and role contract PASS. Genuine P36 selection BLOCKED. |
| C04 | Typed AXNODE grammar, immutable hashing and versions | golden canonical hashes, duplicate keys/cycles/unsafe ops rejected | 004 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C05 | AXNODE graph persistence, backup & rollback | crash/reopen/migration, parent invalidation, no overwrite | 005, 006, 007, 008 | Disposable fixtures exercised. Customer data and hardware power loss NOT_RUN. |
| C06 | Lexical/typed/graph retrieval with provenance | relevant/negative queries, determinism, zero prompt leakage | 009, 011 | Disposable fixtures exercised. Customer data and hardware power loss NOT_RUN. |
| C07 | Separate local working/episodic/semantic/procedural/negative memory | retention/security isolation, restart trace, no raw Git uploads | 010, 011 | Disposable fixtures exercised. Customer data and hardware power loss NOT_RUN. |
| C08 | ProblemModeler constraints/unknowns | contradictory/missing evidence produces UNKNOWN not invented facts | 012 | Disposable fixtures exercised. Customer data and hardware power loss NOT_RUN. |
| C09 | Designer alternatives/trade-off oracle | reproducible ≥2 alternatives or explicit infeasibility | 013 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C10 | Hierarchical subgoal DAG planner | cycle/invalid effect rejection, valid plans on unseen fixtures | 015 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C11 | Bounded search & cost-aware ranking | search caps, cancellation, baseline comparison | 016 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C12 | Existing 13 typed CPU skills compatible/read-only | identical source/receipts against historic test corpus | 017 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C13 | Restricted composition/synthesis DSL | new typed composition; no arbitrary code, bounded depth | 018 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C14 | Independent verifier & counterexample engine | detect seeded wrong proof/forged outcome independently | 019, 020 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C15 | Candidate→ACTIVE proof/promotion & quarantine | holdout/rollback and independent gate; no self-certification | 020, 021 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C16 | Episode outcome ledger with negative memory | trace provenance, verified outcomes only, replay | 022, 023 | Fixture controls exercised. Operational promotion/side effects HOLD. |
| C17 | Local StrategyLearner with no-regression | measured uplift or fallback, separated train/test families | 023, 024 | Fixture controls exercised. Operational promotion/side effects HOLD. |
| C18 | Safe synthetic curriculum & coverage | deterministic fixtures, diversity/leakage checks, no real execution | 025 | Fixture controls exercised. Operational promotion/side effects HOLD. |
| C19 | EvidenceLedger, claim truth/uncertainty model | stale/contradicted facts tracked, abstention on no oracle | 014 | Fixture controls exercised. Operational promotion/side effects HOLD. |
| C20 | PolicyGate capability and approval hash | prompt injection and no-consent action denied | 027 | Fixture controls exercised. Operational promotion/side effects HOLD. |
| C21 | Player execution receipts/compensation | sandbox idempotency, cancellations, rollback, no original write | 028, 029, 030 | Fixture controls exercised. Operational promotion/side effects HOLD. |
| C22 | Optional my_local_ai/HAE/LA adapter contract | stub-only handshake, explicit consent and disabled-by-default | 031 | Fixture controls exercised. Operational promotion/side effects HOLD. |
| C23 | Windows local resource scheduler | RSS/latency/cold start measured, CPU offline fallback | 032 | Fixture controls exercised. Operational promotion/side effects HOLD. |
| C24 | EAI-owned explanation and trace UI/CLI | source links, uncertainty, plan inspection, accessible offline | 033 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C25 | Benchmarks B0/B1/B2 on OOD task families | exact SHA, no-leak, effect sizes and failure set reported | 026 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C26 | Backup/restore, privacy & supply-chain review | synthetic migration/restore/provenance and security review | 006, 007, 008, 029, 030 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C27 | Research lane: original language/causal/general model | separate bounded experiment; no premature GPT parity claim | 033 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C28 | Acceptance split & independent audits | implementation vs validation evidence matrix & owner GO held | 002, 033, 042 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C29 | OFF/ON detachable provider contract and no-SDK offline | OFF identical baseline, no remote import or network bytes, stable schemas | 034 | Local controls exercised. Live operation/entitlement BLOCKED. |
| C30 | Opt-in Hydrogen synthetic/public ResearchPacket & preview | private prompt exfil denied; ≤500 chars; separate consent | 035, 039 | Local controls exercised. Live operation/entitlement BLOCKED. |
| C31 | Zero-paid-tier guard, quota budget and circuit-breaker | block unknown/paid accounts; RPM/TPM/RPD local limits, 429 fallback, no paid switch | 036, 040 | Local controls exercised. Live operation/entitlement BLOCKED. |
| C32 | Untrusted CandidateIdea DSL/AXNODE quarantine | no direct action/promotion; independent verifier rejects forged model response | 037 | Mapped local suites exercised. Independent acceptance NOT_RUN. |
| C33 | Same-task OFF/ON sandbox A/B and true live-data attribution | paired baseline uplift/failure metrics, external provenance preserved | 038, 040 | Local controls exercised. Live operation/entitlement BLOCKED. |
| C34 | Safe disable/removal, late-response and crash recovery | switching OFF retains local plans/episodes, ignores late replies, no network | 034, 041 | Local controls exercised. Live operation/entitlement BLOCKED. |
| C35 | Remote-only controlled research consent and privacy compliance | live use BLOCKED until separate user GO and entitlement review | 035, 039 | Local controls exercised. Live operation/entitlement BLOCKED. |
| C36 | OFF independent competence and no-forced-cloud UX | complete goal/design/action path works offline with Qwen absent or present | 034, 041, 042 | Mapped local suites exercised. Independent acceptance NOT_RUN. |

## Legacy P0–P38

The legacy numbered engineering milestones are separate from today's P1 implementation and P2 acceptance stages. The roadmap also uses phase names P0–P5. Provider use, sales and owner approval have separate gates.

| Milestone | Subject | Executed suites | Observed scope |
|---|---|---|---|
| P0 | Rule parser, offline CPU, tools and durable store | [core](../tests/test_core.py) 18P, [memory](../tests/test_memory.py) 12P, [workflows](../tests/test_workflows.py) 3P | Real SearXNG NOT_RUN |
| P1 | Everyday CLI, memory, bounded histories | [b0_cli](../tests/test_b0_cli.py) 7P, [b1_cli](../tests/test_b1_cli.py) 6P, [memory](../tests/test_memory.py) 12P, [desktop_workstation](../tests/test_desktop_workstation.py) 11P | 3B target model measurement BLOCKED |
| P2 | Compare and streaming read-only analysis | [analysis](../tests/test_analysis.py) 11P, [csv_analysis](../tests/test_csv_analysis.py) 9P | Local synthetic PASS |
| P3 | CSV claims and verification | [verify_csv](../tests/test_verify_csv.py) 19P | Local synthetic PASS |
| P4 | Keyed reconciliation | [reconcile_csv](../tests/test_reconcile_csv.py) 23P | Local synthetic PASS |
| P5 | Multi-metric diagnosis | [diagnose_csv](../tests/test_diagnose_csv.py) 25P | Local synthetic PASS |
| P6 | Typed plan execution | [plan_engine](../tests/test_plan_engine.py) 24P | Local synthetic PASS |
| P7 | Multi-domain goal routing | [goal_dispatch](../tests/test_goal_dispatch.py) 16P | Local synthetic PASS |
| P8 | Verified typed receipts | [receipt_guard](../tests/test_receipt_guard.py) 21P | Local synthetic PASS |
| P9 | Display integrity | [receipt_evidence_p9](../tests/test_receipt_evidence_p9.py) 10P | Local synthetic PASS |
| P10 | Task portfolio | [task_portfolio_p10](../tests/test_task_portfolio_p10.py) 19P | Local synthetic PASS |
| P11 | Critical path and deadline | [task_schedule_p11](../tests/test_task_schedule_p11.py) 19P | Local synthetic PASS |
| P12 | Verified batches | [goal_batch_p12](../tests/test_goal_batch_p12.py) 19P/1S | Local synthetic PASS |
| P13 | Offline doctor | [offline_doctor_p13](../tests/test_offline_doctor_p13.py) 14P | Local synthetic PASS |
| P14 | Dependency pipelines | [goal_pipeline_p14](../tests/test_goal_pipeline_p14.py) 18P | Local synthetic PASS |
| P15 | Manifest builder | [manifest_builder_p15](../tests/test_manifest_builder_p15.py) 18P/1S | Local synthetic PASS |
| P16 | CSV quality gate | [csv_quality_p16](../tests/test_csv_quality_p16.py) 27P/1S | Local synthetic PASS |
| P17 | CSV schema drift | [csv_schema_drift_p17](../tests/test_csv_schema_drift_p17.py) 26P/1S | Local synthetic PASS |
| P18 | SQLite audit | [sqlite_table_audit_p18](../tests/test_sqlite_table_audit_p18.py) 19P/1S | Disposable SQLite PASS |
| P19 | CPU relationship discovery | [csv_relationships_p19](../tests/test_csv_relationships_p19.py) 21P/1S | Local synthetic PASS |
| P20 | Local evidence search | [local_evidence_search_p20](../tests/test_local_evidence_search_p20.py) 19P/1S | Local synthetic PASS |
| P21 | Resource schedule | [resource_schedule_p21](../tests/test_resource_schedule_p21.py) 19P | Local synthetic PASS |
| P22 | Robust outliers | [robust_outliers_p22](../tests/test_robust_outliers_p22.py) 18P/1S | Local synthetic PASS |
| P23 | CSV advisor | [csv_advisor_p23](../tests/test_csv_advisor_p23.py) 14P/1S | Local synthetic PASS |
| P24 | Goal selector | [goal_selector_p24](../tests/test_goal_selector_p24.py) 18P/1S | CPU/fixture PASS |
| P25 | Verified report export | [report_export_p25](../tests/test_report_export_p25.py) 12P | Local synthetic PASS |
| P26 | Exact-hash human execution gate | [approved_run_p26](../tests/test_approved_run_p26.py) 12P | Separate synthetic authorization PASS |
| P27 | Portable zipapp | [portable_p27](../tests/test_portable_p27.py) 11P/1S | Local synthetic PASS |
| P28 | Quick goals | [quick_goal_p28](../tests/test_quick_goal_p28.py) 15P | Local synthetic PASS |
| P29 | Distribution shift | [distribution_shift_p29](../tests/test_distribution_shift_p29.py) 16P | Local synthetic PASS |
| P30 | Portable journey | [portable_journey_p30](../tests/test_portable_journey_p30.py) 6P | Local synthetic PASS |
| P31 | Key coverage | [key_coverage_p31](../tests/test_key_coverage_p31.py) 18P/1S | Local synthetic PASS |
| P32 | Source-free customer review | [customer_review_p32](../tests/test_customer_review_p32.py) 12P/1S | Synthetic review PASS |
| P33 | Offline candidate archive | [customer_candidate_p33](../tests/test_customer_candidate_p33.py) 10P | Unsigned synthetic package PASS |
| P34 | Extract / run / verify end to end | [customer_candidate_p33](../tests/test_customer_candidate_p33.py) 10P | Subprocess and independent verifier PASS |
| P35 | Canonical detached ZIP checksum | [customer_candidate_p33](../tests/test_customer_candidate_p33.py) 10P, [windows_candidate_p37](../tests/test_windows_candidate_p37.py) 5P | Synthetic ZIP PASS |
| P36 | Genuine localhost input classification | [local_qwen_acceptance_p36](../tests/test_local_qwen_acceptance_p36.py) 8P | Harness PASS. Default model absent. Installed alternate abstained. Genuine selection BLOCKED. |
| P37 | Native Windows CMD candidate | [windows_candidate_p37](../tests/test_windows_candidate_p37.py) 5P | Real Korean/space CMD journey PASS |
| P38 | Offline candidate classifier comparison | [model_candidate_benchmark_p38](../tests/test_model_candidate_benchmark_p38.py) 10P | Synthetic comparator PASS. Owner-pinned real comparative predictions NOT_RUN. |

## P2 queue

| Gate | Acceptance target | Astra evidence and remaining scope |
|---|---|---|
| EAI-P2-01 | Exact SHA full compileall, whole type/static and mandatory existing CI, 13-goal baseline nonregression | Local compile, type, offline suite and required CI PASS. |
| EAI-P2-02 | DB integrity, synthetic crash/restart, sidecar epoch/coherence and isolated restores | Isolated SQLite WAL/restore/integrity fixtures PASS. Physical power loss NOT_RUN. |
| EAI-P2-03 | Architect unknown/contradicted claims, bounded plans, legacy solver parity | Bounded candidates, contradiction and unknown handling exercised. |
| EAI-P2-04 | Counterexample independent oracle, forged proof rejection and ACTIVE hold | Independent oracle fixtures, counterexamples and ACTIVE refusal exercised. |
| EAI-P2-05 | Verified-only learner, heldout/OOD family split, no regression quantified | Heldout and admission fixtures exercised. Real-world quality gain UNMEASURED. |
| EAI-P2-06 | Player action scope/idempotency/rollback, adapter cross-repo guards and security | Typed simulated policy and fenced adapters exercised. Real side effects BLOCKED. |
| EAI-P2-07 | Hydrogen default OFF/no network, mock/quarantine, approved free-tier/consent gated live checks | OFF/mock/quarantine exercised. Live per-send approval and account entitlement BLOCKED. |
| EAI-P2-08 | Owner Win11 CPU RSS measured offline and no real customer data | Host and new sandbox startup/RSS plus isolated workflow measurements completed. |
| EAI-P2-09 | CLI output/errors and optional actual browser FE accessibility/UX E2E | CLI and native keyboard/interaction tests exercised. Browser NOT_APPLICABLE. |
| EAI-P2-10 | Full acceptance matrix and independent Codex/Astra review + High GO decisions | Astra review packet delivered. Independent review and High NOT_RUN. |

Canonical source queues retain their historical states. The decision on official P2 belongs to High after the independent review.
