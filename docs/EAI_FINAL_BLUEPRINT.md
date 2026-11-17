> **2026-11-17 P1 candidate (not accepted):** Code SHA `b22a877e55ddab010ceb5c006e9d5016704e6366` adds strict cognitive contracts, parse-only AXNODE and NullProvider/OFF gate; 19 tests authored, NOT_RUN. Full EAI cognition runtime/Graph/Synthesizer/Learner/Player/Hydrogen provider remains prospective. [Queue](EAI_INSTANT_TASK_QUEUE.md) is authoritative for evidence.

# EAI — Independent Cognitive Architect & Player: Canonical Final Blueprint
**Version:** EAI-BP-V3.1 | **Owner decision:** 2026-11-17 KST | **Status:** DESIGN_CANONICAL / IMPLEMENTATION_NOT_CLAIMED
**Repository:** hibi89/EAI | **Active documentation branch:** feature/kmong-eai-85-p31-20261112
**Authority:** Current owner request > safety/approval constraints > this long-term EAI blueprint and ADR-0002 > project AGENTS > historical product notes. This document elaborates ADR-0002; it does not authorize production, paid usage, remote prompt transfer, privilege changes or changes to other repositories.

## 0. Non-negotiable identity and product separation
**EAI is an independent, progressively general-purpose LOCAL AI: the ARCHITECT who defines a problem, develops alternative designs and reasoning strategies; and the PLAYER who safely acts, observes, verifies and learns.** It should become more capable on previously unseen tasks by creating and reusing independently validated knowledge/logic. This is an *aspirational research target*, not a claim of achieved GPT-class intelligence.
**my_local_ai is a separate execution-centric coding/instruction-following local AI product**, like a Codex-style development factory. EAI is not renamed my_local_ai and is not a subordinate coding agent. EAI may eventually export a reviewed, scoped `PlanSpec`/`ActionSpec` to my_local_ai, AX Dev Factory, HAE or LA via optional adapters, but **none is a runtime dependency, no other repo is edited here, and execution/approval authority does not transfer**. EAI must solve non-coding tasks.
Historical Kmong packaging/13 typed CPU goals remain preserved as an implementation baseline, not the definition/denominator of independent-general-intelligence success. Legacy 85% is a *historical provisional product score* only; V3 implementation and verification rates are `UNASSESSED` until an owner-approved fixed requirement/acceptance weighting. `RELEASE HOLD` on existing product. Never claim AGI, general reasoning competence, Windows/Qwen verification or a published product from docs.

## 1. Design-space comparison and selection
| Option | Cognition owner | Quality / generalization | Local cost | Audit / maintenance | Decision |
|---|---|---|---|---|---|
| A. Hard-coded 13+ fixed CPU solvers only | EAI CPU | Deterministic, narrow; new domain needs manual code | Low | Excellent, bounded | Retain as verified foundation; insufficient final target |
| B. AXNODE as pure file/RAG lookup | EAI selects stored answers | Reuses prior patterns; cannot invent or certify a novel algorithm | Low | Moderate, stale/error propagation | Memory component only |
| C. Qwen/local LLM writes the solution/plan | Model | Broad fluency, hallucinations, model dependence | Medium/high | Poor independent ownership | **Reject as EAI final authority (ADR-0002)**; optional INPUT parser only |
| D. EAI-owned typed symbolic synthesis + case memory + independent verifier + small learned search policy | EAI CPU | Composable transferable strategies within proven domains; still not GPT-level generality | Low first, bounded CPU-heavy search later | Strong provenance if governed | **Selected modular core** |
| E. Train original generalized foundation model now | Original ML model | Potential long-range goal, no credible immediate performance guarantee | Infeasible for GTX1050 Ti/16GB to match GPT-scale training | High research risk | Later separate, measurable research lane, not implementation promise |

**Hybrid chosen:** typed explicit problem representations, rule/constraint solvers, bounded hierarchical planning & search, AXNODE procedural/semantic/episodic memory, verified program synthesis, controlled experimentation, small local strategy ranker, conservative executor, grounded response generation. Optional model adapters supply intent classification only and never become hidden problem-solvers. Expand competence by validated library growth, not by counting nodes or rewriting a model's claims.

## 2. End-to-end cognition and action contract
`User goal → RuleIntentParser / opt-in loopback Qwen INPUT-only → validated IntentSpec → EAI ProblemSpec(world state, goals, constraints, unknowns, data rights) → Hypothesis/DesignSpec alternatives → AXNODE retrieval and world/causal model → hierarchical PlanGraph and StrategySpec candidate synthesis → EAI-owned bounded search/solver → separate Verifier & EvidenceLedger → DecisionSpec with confidence/abstention → capability/owner PolicyGate → optional Player ActionSpec → observation/reconciliation/rollback → Episode and Feedback → AXNODE promotion and StrategyLearner → EAI-owned ResultSpec and deterministic renderer.`
The architecture MUST support two loops:
- **Designer loop:** ask what is being solved; decompose, infer constraints, propose 2+ alternative plans; compare resource, reliability and reversibility; identify missing evidence; generate testable hypotheses and counterfactuals; output reviewable design with expected outcomes, assumptions, failure cases and proof obligations. Can stop safely at DESIGN_ONLY.
- **Player loop:** accept a *separately authorized* plan, select only allowlisted actions, execute within quotas, observe external state, verify postconditions, repair safely, pause/rollback on unexpected effects. No model-generated privileged write is executed.
Allowed auto-execution initially only on isolated synthetic or explicit read-only local tasks. A plan is not permission. Human approval for payments, external transmission, public release, credentials/permissions, destructive edits, original/customer data, deployments or irreversible actions; preserve explicit approval binding to exact plan hash, capabilities, scope and expiry.
The architecture distinguishes `facts` (independently verified), `observations` (source identified), `hypotheses` (not proven), `candidate logic` (unverified), `unknowns` and `user preferences`. Missing evidence triggers clarification/abstention, not fabricated results. Never treat fetched pages, AXNODE prose, a Qwen classification or tool output as higher-priority instructions.

## 3. Canonical modules and typed contracts
| Module | Input → output | Responsibility and hard invariant |
|---|---|---|
| IntentPort | user text → `IntentSpec` | CPU rule-first; Qwen localhost optional, JSON allowlist only; unsupported remains explicit |
| ProblemModeler | IntentSpec + authorized observations → `ProblemSpec` | Goals, hard/soft constraints, domain facts, scope, uncertainty, success oracle |
| DesignEngine | ProblemSpec → `DesignSpec` | ≥2 viable alternatives where applicable, trade-offs, assumptions, threat model, tests |
| WorldModel | Evidence + postconditions → `StateGraph` | Typed entities, relations, temporal facts, contradiction and source age handling |
| AXNODE Store/Index | versioned node files ↔ SQLite catalog | Immutable versions, lineage, capabilities, lifecycle, retrieval provenance |
| RetrievalRouter | ProblemSpec → ranked AXNODE references | Exact type/constraints → lexical FTS5 → graph neighborhood → optional measured local embedding ranker; log rejected candidates |
| StrategySynthesizer | validated nodes + typed grammar → `StrategySpec` | Compose, specialize, reorder, guarded branch, bounded loops, extract shared subroutines; no arbitrary Python generation/exec |
| Planner/Search | StrategySpec + state → `PlanGraph` | HTN-like decomposition, DAG and constraint propagation; bounded A*/beam/branch-and-bound, selectively MCTS only if tested; top-k alternatives |
| SolverRegistry | allowlisted typed op → `SolverReceipt` | Reuse current 13 CPU solvers and future domain modules; deterministic/seeded execution where possible |
| IndependentVerifier | evidence + outputs → `VerificationReceipt` | Independent recomputation/property/metamorphic/oracle checks; do not self-certify with original solver |
| PolicyGate/Player | PlanSpec + exact consent → `ActionReceipt` | Least-privilege capability tokens, side-effect classification, dry-run, quotas, audit, idempotency, rollback |
| ExperienceStore | observations, traces → `Episode` | Local working, episodic, semantic, procedural, negative and policy memory; privacy/TTL/confidence |
| StrategyLearner | vetted episodes → model/ranking metrics | Local simple bandit/logistic/tree/heuristic scoring; only learns on separately checked outcomes, no self-reward |
| CurriculumEngine | gaps + benchmark catalog → proposed practice | Safe synthetic tasks, novelty/difficulty/diversity budgets; never self-authorize real-world actions |
| Result/Explanation | proofs/limits → `ResultSpec` | EAI-owned templates first; cite evidence, alternatives, confidence/unknown; optional original local NLG research isolated |
| HardwareScheduler | workload + measured resources → budget | CPU-first; bounded RAM/time/disk; optional GPU only after local benchmark; cancellation and degraded offline mode |

Minimum stable contracts: `ProblemSpec(v1): id, goal, domain, state_refs, assumptions, hard_constraints, objectives, oracle, permissions, budget, risk`; `PlanSpec(v1): problem_sha256, node_refs+hashes, ordered typed steps, effects, expected_observations, verification, cost/risk, consent_scope`; `Episode(v1): plan_hash, node_versions, anonymized context features, outcomes, verifier refs, costs, failure class, timestamp`; `EvidenceLedger(v1): claim→source SHA/URI+time+rights+verification state, lineage, contradiction`. Use canonical JSON and SHA-256 of canonical bytes; version migration is additive and reversible.

## 4. AXNODE: first-class *reasoning logic* artifact, not a prompt file
`.axnode` is **EAI-defined** versioned UTF-8 canonical JSON (not an established industry standard). A node is a *verifiable procedure/abstraction/constraint/rule*, not merely an answer or chat transcript. Nodes include `concept`, `predicate`, `operator`, `strategy`, `workflow`, `verifier`, `hypothesis`, `failure_pattern`, `abstraction` and `policy_reference`; episodes remain in the private local DB, not automatically exported to GitHub. Nodes have stable namespace ID + immutable content hash/version, semantic signature (typed input/output), pre/postconditions, side-effect capabilities, applicability/negative constraints, provenance, parents/dependencies, bounded steps, test/oracle refs, empirical evidence, failure cases, license/privacy tags, status, cost profile. Store only reviewed non-sensitive *definitions* in Git.
Example **DESIGN ONLY** (not an installed node):
```json
{
  "schema": "eai.axnode.v1",
  "id": "data.csv.key_diff",
  "version": 1,
  "kind": "strategy",
  "status": "CANDIDATE",
  "signature": {"inputs": {"a": "csv_ref", "b": "csv_ref", "key": "column"}, "output": "difference_receipt"},
  "pre": ["authorized_read_only_sources", "key_column_exists"],
  "post": ["source_hashes_unchanged", "independently_verified_receipt"],
  "steps": [{"skill": "csv.reconcile.v1"}, {"skill": "evidence.verify_receipt.v1"}],
  "capabilities": ["local.read"],
  "parent_hashes": [],
  "tests": {"unit": [], "heldout": [], "negative": []},
  "evidence": [],
  "provenance": {"author": "EAI_DESIGN", "source": "local_verified_only"},
  "budget": {"max_steps": 5, "max_seconds": 60}
}
```
Parser MUST reject unknown schema, duplicate JSON keys, recursive cycles, invalid step IDs, unsafe path traversal, out-of-scope tools, mutable/forged parent hashes, oversized payload and invalid dependency versions. Canonicalize JSON deterministically; content-address by SHA-256; signature or authenticated provenance where needed, without claiming a digest proves authenticity. No shell/Python/eval/import/code bodies in active v1 nodes.
Lifecycle: `DRAFT → CANDIDATE → TESTED → VERIFIED → ACTIVE`; failures → `QUARANTINED`; replacements → `DEPRECATED`, with immutable audit trail and rollback to previous ACTIVE hash. **Only a separate verifier may promote** a candidate. Success on the training examples alone is never enough. New versions never silently overwrite existing nodes. Dependency graph invalidates/re-evaluates descendants if a parent is withdrawn or contradicted. Cap node count/graph depth/branch factor by measured budgets and garbage-collect *indexes only*, never delete evidence without retention approval.
Local storage: `nodes/*.axnode` immutable sanitized library; SQLite WAL catalog `nodes, edges, episodes, observations, decisions, verifier_receipts, evaluation_runs, approvals, quarantine` with foreign keys and migration/backup/restore; FTS5 lexical search first (Korean tokenization quality measured), exact signature filter and graph neighbors; optional on-device embeddings only after measurable lift. Avoid hand-building a production vector database prematurely. Idempotent atomic file+DB publication with staging/temp + hash verification and crash recovery ledger. Git never receives raw prompts, private episodes, model weights, tokens, owner documents or live customer data.

## 5. How EAI actually *creates* thought/logic
Current implementation: developers write 13 typed CPU goal handlers, `RuleGoalPlanner` selects fixed solver branches, `goal_pipeline` executes an explicit SHA-pinned goal DAG, and `storage.py` retains notes/turns/cache. **It currently does NOT prove automatic generation/generalization/promotion of novel reasoning procedures.** Implement new loop in stages:
1. **Observe & frame:** derive ProblemSpec; collect only permitted evidence and explicit unknowns; assign objective function and independently testable oracle. If no oracle, keep a hypothesis, never auto-promote.
2. **Retrieve & diagnose:** find exact applicable AXNODE by signature/precondition and authority; use retrieval score as proposal, never truth. Retrieve negative cases/failure patterns too.
3. **Design alternatives:** instantiate existing strategies, decompose subgoals (HTN/DAG), constrain resources/permissions, rank ≥2 distinct candidates when available. For open-world goals, form multiple falsifiable hypotheses and targeted observations.
4. **Synthesize:** constrained DSL grammar with typed compose/sequence/branch/bounded repeat/reorder/parameterize, constraint solving and subroutine abstraction. Enumerative/A*/beam or synthesis-by-examples with search budgets; optional small ML guidance trained on verified outcomes. Reject cycles, invalid effects and unreachable verifier conditions.
5. **Sandbox experiment:** synthetic/disposable data only by default; generate independent tests, metamorphic relations, property-based mutations, counterexamples and boundary cases. Distinguish test generator from evaluator, seeded holdout/test fixtures.
6. **Independent check:** compare candidate against simpler baseline on held-out tasks, safety/regression oracle and cost/resource budgets; require actual observed improvement or strictly preserved correctness with documented efficiency gain. Unverifiable subjective outputs stay hypotheses.
7. **Abstract & store:** deduplicate/subsume identical or dominated strategies, extract reusable subroutine with parent lineage; insert candidate atomically, then activate only after separate proof gate. Record failed paths as *negative memory*, not accepted solutions.
8. **Learn the selector:** train/calibrate an on-device ranker from *verified* successes/failures and cost; train/validation/test split by scenario families and time; never train from agent self-claims. Monitor drift, catastrophic forgetting, poisoned episodes and reward hacking; restore last-known-good model if regression.
9. **Continuous curriculum:** choose safe, varied, moderately challenging synthetic problems from capability gaps; prove transfer on unseen domains/families, not just more tests on the same CSV.
Useful precedents (inspiration, not drop-in implementation/verified EAI features): DreamCoder's reusable program abstractions and wake/sleep search (https://doi.org/10.1145/3453483.3454080); Voyager's skill library/curriculum/feedback (https://arxiv.org/abs/2305.16291) **depends on GPT-4 and is NOT independently cognitive**; SQLite FTS5 official API (https://www.sqlite.org/fts5.html). Do not copy licenses, code or restricted datasets blindly.

## 6. Generality path: from expert local solver to designer/player
- **Level 0 / existing baseline:** 13 deterministic typed CPU goal kinds, local CLI, source hashes, independent receipts, synthetic Linux CI; official current V3 acceptance UNASSESSED.
- **Level 1 / knowledge reuse:** AXNODE schema, retrieval, traceable selection, episodic outcomes, reliable offline no-model operation. Capability is *memory and reapplication*, not novel intelligence.
- **Level 2 / multi-domain planning:** ProblemSpec + constraints + HTN/DAG + search alternatives over 13+ tools; explicit domain transfer with verified types and postconditions; generate inspectable designs. Handle contradictory evidence and unknowns.
- **Level 3 / verifiable invention:** constrained program synthesis and counterexample-guided refinement, novel compositions, abstention, generated test suites and promotion/rollback.
- **Level 4 / lifelong task adaptation:** curated episodes, strategy ranker, systematic evaluation on unseen task families, safe synthetic curriculum, measured reduction in human-authored rules per solved task.
- **Level 5 / player:** permission-scoped execution of local tasks, reproducible plan→act→observe→verify→repair with dry-run and compensation; later external integrations only with authorization; optional interface to my_local_ai without authority inversion.
- **Level 6 / open-domain research:** richer causal/temporal models, original local natural-language generation/abstraction, new domains, multimodal understanding and an independently trained cognitive model as **research tracks**. No fixed GPT-parity deadline/claim. Natural language competence cannot be inferred from tool count.

## 6A. Dual-mode best-available architecture — detachable Gemini 4 Hydrogen (V3.1)
[ADR-0005](ADR-0005_HYDROGEN_DETACHABLE_DUAL_MODE_20261117.md) is the **canonical detailed design** for Hydrogen ON/OFF. Earlier [ADR-0004](ADR-0004_HYDROGEN_OPTIONAL_EVALUATION_20261117.md) remains an historical P38 offline benchmark and its future input-only limitation is superseded **only for quarantined, non-authoritative synthetic research suggestions**. ADR-0002 still prohibits Qwen-generating EAI's final solutions: local Qwen classifies INPUT only. EAI maintains full architecture, execution/approval and final decision authority regardless of provider.
- **OFF (DEFAULT, zero cloud API):** Rule parser + optional localhost Qwen INPUT parser + EAI-own ProblemModeler, AXNODE graph, LogicSynthesizer, hierarchical planner, independent verifier, StrategyLearner, PolicyGate/Player and own response; deterministic offline fallback when even Qwen is absent. OFF never reads API key, initializes a Hydrogen SDK or connects to the network. All reasoning/plan and local memory remain portable and usable.
- **ON (RESEARCH_OPT_IN, free-only):** independently produce the OFF candidate **first**, then on explicit user approval and validated Google free project entitlement send only previewed public/synthetic minimal ResearchPacket ≤500 chars and pre-approved IDs to optional Hydrogen candidate-provider module. Hydrogen suggests alternative experiment ideas, typed logic candidates or counterexample hypotheses; EAI alone constrains, tests, verifies and decides. Outside origin is permanently labelled, no automatic promotion or remote planner/tool/Player authority.
- **Failure/DETACH:** 429/RPM/TPM/RPD, 401, tier unknown, disallowed content, timeout or model disabled → local output + diagnostic/circuit breaker, not paid fallback. Toggling OFF keeps all offline local state and cancels/ignores outstanding sends. Hard $0 paid budget is policy, not a promise that an unknown billing account cannot charge; live use requires verified free tier and a **separate per-send consent**. Rates differ by account/project; do not invent quotas.
- **Evaluation:** Same blind tasks and hash-pinned EAI engine for OFF vs mock ON vs later approved real ON. Compare accuracy/transfer, verification failures, resource/latency, tokens/quota and security leak prevention. No claims of automatic superiority, generalized intelligence or zero bill without evidence.
- **Provider boundary:** NullProvider and lazy HydrogenResearchAdapter only implement `propose(ResearchPacket) → CandidateIdea[]`, never `solve` or `execute`. External proposals are sandboxed, provenance-labelled and must not rewrite verified AXNODE or independent EAI knowledge automatically. The optional provider is not a core dependency.
- **Current status:** V3.1 dual-mode extension is **DESIGN ONLY**. Existing 13 CPU goals, P26 SHA approvals, P38 offline comparator, user data and release HOLD unchanged; Hydrogen live API not called.

## 7. Security, provenance, rights and recovery gates
- Local-first, free-default, offline functionality mandatory. On-device Qwen/Ollama only optional INPUT parsing; no Qwen-generated final solution, chain-of-thought impersonation or final decision. P38 Hydrogen only offline synthetic comparator; remote API/GitHub worker remains blocked pending explicit separate authorization. Do not silently switch provider because local parser fails.
- Model/retrieved/AXNODE content is untrusted. Strict parse, allowlisted typed operators, no arbitrary import/exec/eval, prompt-injection resistant trust boundaries, source provenance, file canonicalization, symlink/path restrictions, resource/time limits, input size caps, loopback endpoint pinning, network default OFF.
- Capability tiers: `PURE/READ_LOCAL` (default, authorized inputs), `WRITE_SANDBOX` (explicit scoped consent), `WRITE_ORIGINAL/EXTERNAL_SEND/GITHUB_WRITE/DEPLOY/PAY/PERMISSIONS` (owner per-action approval); separate design, proposal, action and publish identities. Never derive owner approval from a model answer or an AXNODE flag.
- Side effects: preview/diff, exact artifact hash and proposed target, atomic commit, dry-run; conditional retry only when idempotent; action receipts with before/after hashes, failure classification, cancellation, rollback/compensation. No silent production changes, destructive DB, secret upload or public dataset publication.
- Secure local DB: migrations transactional with pre-migration backup; integrity and restore drills; private indexes, ACL where supported, retention/consent tagging, export sanitization and evidence deletion path only on explicit instructions. No implied perfect deletion from backups.
- Error handling: two unchanged failed approaches → stop that approach, isolate blocker and move to independent READY. Fail CLOSED on absent model, missing evidence, resource exhaustion, contradiction, verifier disagreement, lost approval, stale dependencies.
- Provenance is not certainty: SHA checks integrity, not source truth; confidence calibrated against independent ground truth; distinguish test, mock, Windows, GPU, real Qwen and buyer/production proof.

## 8. Hardware/runtime and UI
Target Windows 11 Pro, Python 3.11+, GTX 1050 Ti, 16GB RAM, optional local Qwen3 4B at owner's installed Ollama location. CPU-first SQLite + standard library for R0/R1; optional modest dependencies only after free/offline/reproducible evaluation. Hardware scheduler measures process RSS, cold/warm latency, search states, disk growth and model startup; applies configurable concurrency/search/iteration budgets. No invented throughput, no promise 24/7 uptime, no required paid GPU/cloud. Qwen may be absent with deterministic fallback. GPU layers, embeddings, quantization and memory fitting are experiments, not certified optimizations.
CLI first: `eai design <goal>`, `eai plan <goal>`, `eai inspect-plan`, `eai simulate`, `eai run-approved`, `eai remember/axnode find/history/eval` as **proposed interfaces**, not existing CLI commands. Minimal local visual graph/explanation UI only after design+player trace accepted; accessibility, offline, keyboard support and clear simulation/real-action labels. No SaaS / Vercel deployment requirement.

## 9. Evidence-driven evaluation, release and success criteria
Three baselines on the SAME held-out set: (B0) existing single fixed CPU solver; (B1) AXNODE retrieval-only; (B2) planner+synthesis+learning. Also compare optional parser to CPU literal baseline without granting it solution authority.
Separate families: arithmetic/constraint reasoning, CSV/SQLite analysis, scheduling/optimization, evidence reconciliation, novel task composition, conflict/incomplete information, adversarial inputs, real-world approved player tasks. Train/test split by *problem family, not only rows*; quarantine benchmark leakage and generated fixture duplicates.
Metrics reported with sample sizes and exact SHA: unseen-task success/accuracy; certified correctness and counterexample rate; unsupported abstention calibration; plan validity; novelty/generalization transfer; exact verification recall/false-positive; regressions; median/P95 latency; peak RSS, disk, GPU, joules when available; search-state budget; verified AXNODE reuse and **measurable uplift vs B0/B1**; risk policy violations count; crash/restore; independent experiment reproducibility. Failed/unsafe candidate suppression matters more than total nodes. Report uncertainty intervals on finite held-out sets.
**Hard gates for promotion:** typed/schema+safety tests PASS; verifier independent from generator; held-out oracle PASS; no high-risk permission escalation; equivalence or demonstrable improvement vs simpler baseline; dependency hashes intact; negative/failure cases stored. **Hard gates for player:** approve correct plan hash + exact scope, synthetic→sandbox→owner-approved real tests, verified rollback and outcome. **Hard gates for research/general claim:** OOD improvements, multiple distinct task families, reproducible local performance, report failures and blind spots. If unverifiable, `HYPOTHESIS/UNASSESSED`; never auto-promote.
Implementation completion = actually coded BE/FE requirements *before consolidated CI*. Verification completion = separately accepted tests against fixed matrix at exact SHA *after implementation candidate*. When weighting/denominator not approved use `completed REQ / total REQ` + `UNASSESSED`, no arbitrary percentages. Independent Codex/Astra audit and owner acceptance/release permissions are additional gates, not invented percentages.

## 10. Fixed requirements catalog, dependencies and objective acceptance
Requirements below are the **new EAI Cognitive Research V3 scope**, distinct from historical 13-goal/Kmong retail percentage. Status at design publication is `DESIGNED_NOT_IMPLEMENTED` unless already covered by explicit old proof; no automatic completion.
| REQ-ID | Required capability | Dependencies | Minimum acceptance evidence | Risk |
|---|---|---|---|---|
| EAI-C01 | EAI vs my_local_ai scope & trust boundary | ADR-0002 | Neither backend can impersonate the other; no cross-repo edits | L |
| EAI-C02 | Versioned ProblemSpec/DesignSpec/PlanSpec/ResultSpec | C01 | schema round-trip, invalid/unknown fields fail closed | M |
| EAI-C03 | Qwen INPUT-only; CPU fallback | C02 | spy tests prove no final Qwen answer/tool authority | H |
| EAI-C04 | Typed AXNODE grammar, immutable hashing and versions | C02 | golden canonical hashes, duplicate keys/cycles/unsafe ops rejected | H |
| EAI-C05 | AXNODE graph persistence, backup & rollback | C04 | crash/reopen/migration, parent invalidation, no overwrite | H |
| EAI-C06 | Lexical/typed/graph retrieval with provenance | C04,C05 | relevant/negative queries, determinism, zero prompt leakage | M |
| EAI-C07 | Separate local working/episodic/semantic/procedural/negative memory | C05 | retention/security isolation, restart trace, no raw Git uploads | H |
| EAI-C08 | ProblemModeler constraints/unknowns | C02,C06 | contradictory/missing evidence produces UNKNOWN not invented facts | M |
| EAI-C09 | Designer alternatives/trade-off oracle | C08 | reproducible ≥2 alternatives or explicit infeasibility | M |
| EAI-C10 | Hierarchical subgoal DAG planner | C08,C09 | cycle/invalid effect rejection, valid plans on unseen fixtures | M |
| EAI-C11 | Bounded search & cost-aware ranking | C10 | search caps, cancellation, baseline comparison | M |
| EAI-C12 | Existing 13 typed CPU skills compatible/read-only | C02,C10 | identical source/receipts against historic test corpus | H |
| EAI-C13 | Restricted composition/synthesis DSL | C04,C10,C12 | new typed composition; no arbitrary code, bounded depth | H |
| EAI-C14 | Independent verifier & counterexample engine | C13 | detect seeded wrong proof/forged outcome independently | H |
| EAI-C15 | Candidate→ACTIVE proof/promotion & quarantine | C05,C14 | holdout/rollback and independent gate; no self-certification | H |
| EAI-C16 | Episode outcome ledger with negative memory | C07,C14 | trace provenance, verified outcomes only, replay | M |
| EAI-C17 | Local StrategyLearner with no-regression | C16,C15 | measured uplift or fallback, separated train/test families | M |
| EAI-C18 | Safe synthetic curriculum & coverage | C17 | deterministic fixtures, diversity/leakage checks, no real execution | M |
| EAI-C19 | EvidenceLedger, claim truth/uncertainty model | C08,C14 | stale/contradicted facts tracked, abstention on no oracle | H |
| EAI-C20 | PolicyGate capability and approval hash | C02,C19 | prompt injection and no-consent action denied | H |
| EAI-C21 | Player execution receipts/compensation | C20,C10 | sandbox idempotency, cancellations, rollback, no original write | H |
| EAI-C22 | Optional my_local_ai/HAE/LA adapter contract | C20,C21 | stub-only handshake, explicit consent and disabled-by-default | H |
| EAI-C23 | Windows local resource scheduler | C11 | RSS/latency/cold start measured, CPU offline fallback | M |
| EAI-C24 | EAI-owned explanation and trace UI/CLI | C09,C19 | source links, uncertainty, plan inspection, accessible offline | M |
| EAI-C25 | Benchmarks B0/B1/B2 on OOD task families | C14,C17 | exact SHA, no-leak, effect sizes and failure set reported | H |
| EAI-C26 | Backup/restore, privacy & supply-chain review | C05,C20 | synthetic migration/restore/provenance and security review | H |
| EAI-C27 | Research lane: original language/causal/general model | C25 | separate bounded experiment; no premature GPT parity claim | R&D |
| EAI-C28 | Acceptance split & independent audits | C01,C25,C26 | implementation vs validation evidence matrix & owner GO held | H |
| EAI-C29 | OFF/ON detachable provider contract and no-SDK offline | C01,C02,C03,C20 | OFF identical baseline, no remote import or network bytes, stable schemas | H |
| EAI-C30 | Opt-in Hydrogen synthetic/public ResearchPacket & preview | C29,C19,C20 | private prompt exfil denied; ≤500 chars; separate consent | H |
| EAI-C31 | Zero-paid-tier guard, quota budget and circuit-breaker | C29,C30 | block unknown/paid accounts; RPM/TPM/RPD local limits, 429 fallback, no paid switch | H |
| EAI-C32 | Untrusted CandidateIdea DSL/AXNODE quarantine | C13,C14,C15,C29 | no direct action/promotion; independent verifier rejects forged model response | H |
| EAI-C33 | Same-task OFF/ON sandbox A/B and true live-data attribution | C25,C29,C32 | paired baseline uplift/failure metrics, external provenance preserved | M |
| EAI-C34 | Safe disable/removal, late-response and crash recovery | C05,C21,C29 | switching OFF retains local plans/episodes, ignores late replies, no network | H |
| EAI-C35 | Remote-only controlled research consent and privacy compliance | C30,C31 | live use BLOCKED until separate user GO and entitlement review | H |
| EAI-C36 | OFF independent competence and no-forced-cloud UX | C24,C25,C29 | complete goal/design/action path works offline with Qwen absent or present | M |

## 11. Implementation sequence for High→Instant→verification (no work confused with release)
- **R0 protect foundation:** snapshot HEAD/policies/13-goal baseline, strict tests/CI evidence, compatibility fixtures; define scopes/contracts and immutable golden corpus. Do not reimplement working P0–P38.
- **R1 AXNODE memory:** schema/validator/hash, local atomic file+SQLite graph, retrieval, negative memory, no-model proof and CLI inspection. Existing behavior preserved.
- **R2 Architect:** ProblemSpec → alternatives/constraint graph → HTN/typed planner → independent proof obligation + EAI-owned design artifact. Use two+ task families.
- **R3 Invent & verify:** restricted DSL synthesis, bounded candidate search, counterexamples, independent promotion; held-out novel compositions.
- **R4 Learn:** episodic receipts → local ranker/curriculum → measured unseen-family improvements, drift/no-regression/rollback.
- **R5 Player:** permission-gated sandbox action loop, simulate/observe/replan/rollback then owner-approved restricted real tasks; optional cross-app adapters.
- **R6 Original general-language/cognition research:** long-term separate hypothesis-driven experiments and local explanation/NLG; expand domains only if baseline evidence supports generalization.
Implementation work is not authorized implicitly by this documentation-only commit; at next EAI-chat `ㄱ` use [EAI_INSTANT_TASK_QUEUE.md](EAI_INSTANT_TASK_QUEUE.md). Group independent READY tasks; syntax/type/local safety checks immediately, full CI/acceptance after implementation candidate per owner policy. Escalate architecture and high-risk changes. No silent branch switch or main merge.

## 12. No-regression, provenance and explicit omissions
Preserve `feature/local-first-mvp`, active `feature/kmong-eai-85-p31-20261112`, `main`, P31–P38 and Draft PR#1, existing SQLite owner data, P26 exact SHA human authorization, release HOLD, 13 typed CPU goals, prior CI evidence and old percentage as *historical*. Project references: [ADR-0002](ADR-0002_EAI_COGNITIVE_OWNERSHIP.md), [ARCHITECTURE](ARCHITECTURE.md), [ROADMAP](ROADMAP.md), [Hydrogen ADR-0004](ADR-0004_HYDROGEN_OPTIONAL_EVALUATION_20261117.md).
**Design status:** all new R1–R6 features in this document are prospective until source, tests and exact GitHub SHA confirm. No live model run, real Windows device, production, customer files, paid external service, GitHub permissions or commercial release is authorized by adopting this blueprint.
