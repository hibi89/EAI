> **2026-11-19 OWNER FINAL IMPLEMENTER LOCK — V3.2:** Only the **owner (user)** and **web GPT-6 High (this EAI worker)** will implement, integrate, test, and fix this program. Do not assign Astra Max, Codex, Luna, Instant, agents or other model workers without a later explicit owner direction. High owns P0/P1/P2 (including frontend and regression/security/Windows evidence insofar as real tools permit), while the owner handles only required local consent/OS evidence/operational GO. Historical outside-model code is untrusted input to review, not accepted authority. **Self-verified P2 is NOT an independent audit**; any preexisting independent-review release gate is still `NOT_RUN`, not waived by changing workers. No external paid network/real Player/Production/permission change without separate GO. The first user-guided goal draft/editor SWUs W01 and W02 are code candidates, remaining W03–W12 are not accepted by implication.

# EAI V3.2 — Owner-led recovery: real cognitive workstation (2026-11-19 KST)

**Branch:** `feature/eai-v32-owner-rebuild-20261119`  
**Starting source:** Astra review PR #3, `e44977fc4f615fa6a368ff64ec4361ceee99e7b4` (NOT MERGED).  
**Owner decision:** Reject the V3.1 Tk desktop as *finished product experience*; rebuild the frontend and the real Architect/Player/AXNODE user journey. Web GPT-6 High owns P0/P1 implementation, P2 execution and defect fixes, and final integration. Independent audit remains independent.  
**Authority:** user current approval > security/P26/ADR-0002 + cognitive blueprint C01–C36 > central owner standard §0J/§0E > actual SHA/tests. This is an **additive/replacement user-experience contract**; it does not delete original code, requirements, tests, backup, PR, history, or implementation evidence.

## Product identity (do not confuse with MLA)

EAI is an offline-first, independent LOCAL cognitive **Architect + Player + Verifier + AXNODE**. MLA is the separate code-generation/development agent. EAI's goal is to define a problem, construct and compare bounded typed reasoning strategies, run only allowed actions, independently verify outcomes and reuse verified reasoning artifacts. Existing 13 deterministic CPU domain solvers are a foundation, not "general AI completed". A Qwen localhost model may optionally **parse input only**; it is not the final solver, authority, verifier or always-on requirement. The design explicitly does not promise GPT-level open-ended generality on GTX 1050 Ti/16 GB.

## Revised end-user contract

1. **Start with a goal, not a demo arithmetic command.** A large persistent Korean goal composer is the primary entry. Supported literal commands still dispatch to genuine EAIRunner local CPU results. Unsupported but syntactically valid freeform goals become a validated **review-only ProblemSpec draft**, never an attempted shell/tool action. No raw JSON required for the default route.
2. **Problem understanding:** show user-editable goal, available evidence, missing inputs, assumptions, constraints, success oracle, budgets and explicit source/permission scope. Confirm before storing. Missing evidence is UNKNOWN, not fabricated. Local file selection is opt-in and read-scoped.
3. **Architect:** retrieve relevant *actual* local AXNODE evidence and CPU skills, synthesize bounded typed strategies, show 2+ genuinely distinct alternatives **where possible**, dependencies, risks, assumptions, counterexamples, cost/reversibility, provenance and why a candidate was rejected. If zero viable alternatives, show exact blocker and safe next step, not a fake plan.
4. **Player:** chosen exact-hash `PlanSpec` enters explicit scope/permissions review. Default only PURE/READ_LOCAL actions; synthetic/no-op must be labeled clearly. Sandboxed write is never silently upgraded to original data. P26 owner exact-scope approval, side-effect/nonce, active ownership, idempotency and rollback conditions remain mandatory for any later real action.
5. **Verifier + AXNODE:** separate independent evidence/oracle verdict, differentiated integrity/semantic/real-world validation, failed cases and bounded trace. Only independently verified results may be admitted to eligible memory; DRAFT/CANDIDATE never silently ACTIVE. Preserve node provenance, negative examples, lineage and user data ownership.
6. **Session continuity:** recent goals, plans and approved traces stored privately in new versioned local records; resume after restart; no old database migration or destructive writes without a tested backup and separate gate.
7. **Honest interface:** show actual engine (CPU / optional local Qwen input parser OFF), real task status/limits, network OFF, Player authority and evidence status. Do not claim model inference, general reasoning, successful OS action, or verification merely because a hash matches.
8. **Windows EXE:** redesigned operator GUI matching the previously selected AX Dev dark-workstation visual direction, but navigation optimized around *Goal → Alternatives → Approved Player → Verification → AXNODE*, including accessible keyboard and Korean IME. Native Windows executable, local-first, no browser/cloud dependency. Frontend toolkit changes only after dependency/license/build feasibility is checked; existing Tk remains a temporary working implementation, not a release-quality commitment.

## P1 execution (High owns all BE + FE)

Existing `C01–C36`, 42 BE SWUs, FE-C01–C06 / six FE SWUs and source SHA evidence **remain traceable**; the former `48/48` is a V3.1 *source candidate historical snapshot* only, not V3.2 product completion. This owner-approved user journey introduces **12 separately tracked V3.2 SWUs** in `docs/EAI_V32_OWNER_SWU_QUEUE.json`. Never count a doc, mock, screenshot, test count or interface wiring without real caller→callee→outcome as a completed SWU. Preserve historical attempts and dependencies. New denominator is 48 existing + 12 V3.2 additions = **60 source work units tracked, not an official weighted percentage**. Source candidate for old 48 still requires compatibility reinspection after changes.

Dependency/critical path:
- **W01** command → safe goal draft (landed code candidate; real GUI local test 9 PASS, Windows NOT_RUN)
- W02 typed goal session/edit UX → W03 CPU skill/AXNODE discovery and honest capability matching → W04 private local AXNODE workspace bootstrap with explicit scope → W05 end-to-end Architect alternatives/fallback
- W05 → W06 selected exact plan review → W07 safe Player with receipts → W08 independent verification and memory admission; no real-world side effects implicitly enabled
- W02 → W09 frontend navigation/goal-focused layout, W05 → W10 explainable evidence/alternative/trace UI, W07 → W11 cancellation/recovery/history/error paths; these can run in safe parallel waves only with disjoint paths
- W09,W10,W11 → W12 reproducible Windows EXE packaging and native UX acceptance *source preparations*, with true Windows validation in P2

Each wave: latest HEAD/AGENTS/STATUS/source/DAG → 1–6 READY actual coding units → syntax/type/local smoke and any immediate security/DB/F18 gates → safe non-force commit + exact SHA. Full integrated CI/UX/security/E2E bundled in P2 after candidate. No automatic infinite retries: 2+2 per SWU; isolate only blocker and continue independent READY.

## P2: High runs and fixes, but does not self-certify independence

Preserve original `EAI-P2-01..10` acceptance and add V3.2 user-journey obligations (see `docs/EAI_V32_OWNER_P2.md`). High shall run full CI/compile/type, 13-goal non-regression, DB integrity and recovery, bounded reasoning/unknown/forged evidence, Player rejection gates, local Qwen OFF/missing and opt-in input parser, native Windows GUI/IME/scaling/keyboard, unsigned EXE source parity, restart/durable history, performance with actual measured RAM/cold startup and all correct SHA. Fix defects and rerun. Existing Astra Windows 1,092 PASS / 18 SKIP is **historical on another SHA**, not a V3.2 verification pass. Linux virtual-display checks are not physical Win11 acceptance.

Release remains HOLD until required gates PASS + separately conducted independent technical/security review + independent UI/UX review + High final audit + owner explicit GO. High checking its own work is *not* independent audit; if independent actors are unavailable mark NOT_RUN. No forced real Hydrogen, credentials, paid APIs, original/customer data, GitHub write, Production, live Player/ACTIVE, main merge or permission change.

## Status at initial replanning

- `W01`: `IMPLEMENTED_UNVERIFIED` candidate; existing CPU command path preserved, unsupported goal now opens review-only Architect draft; focused Xvfb tests 9 PASS, Python compile PASS. One full Linux Tk combined run terminated with a native Tcl/Python process abort; environmental/cross-thread root cause **UNRESOLVED**, not counted PASS; no Windows rerun.
- `W02..W12`: `READY/DEPENDENCY_BLOCKED` as queued; NOT_IMPLEMENTED unless independently evidenced.
- **Official implementation completion:** `UNASSESSED`; **official verification completion:** `UNASSESSED`; **release:** `HOLD`. No new percent inferred from 49/60 or passing tests.
