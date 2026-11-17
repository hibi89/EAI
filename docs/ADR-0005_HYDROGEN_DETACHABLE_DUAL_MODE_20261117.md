# ADR-0005 — EAI removable Gemini 4 Hydrogen: best OFF/ON dual-path architecture
**2026-11-17 KST | Decision:** ACCEPT DESIGN, REMOTE EXECUTION NOT AUTHORIZED | **Status:** DESIGN_CANONICAL, DORMANT_SOURCE_CANDIDATE, LIVE_AUTHORIZATION_HOLD
**Authority:** Owner request for a detachable free-first Hydrogen option, EAI Final Blueprint V3.1, ADR-0002 EAI cognitive ownership and existing original data/security gates. This ADR supersedes only the **narrow future Hydrogen input-classifier-only scope** in ADR-0004: an *isolated research-only proposal source* may be designed, but NOT an EAI brain, runtime executor, trusted planner, verifier, or final renderer. Existing P38 synthetic benchmark stays unchanged and is NOT evidence of a real model.

> **Implementation status addendum — 2026-11-18:** At source `d998a150697926550248ec040b37fe7a8dcf10af`, the dormant per-send signed REST source path is a provisional P1 candidate. Its result and SQLite reservation now share a payload-bound local correlation ID; safe HTTP status classification is bounded, with no schema migration or prior row rewrite. Mock HTTP/temporary SQLite tests and EAI local checks pass. No real Google request, user credential/private key read, or project entitlement verification occurred. Live runtime remains `HOLD`; P2 and release remain locked.

## 1. Verifiable external facts and uncertainties
- Google 2026-11-12 announcement: https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-hydrogen/ ; official model card https://deepmind.google/models/model-cards/gemini-4-hydrogen/ ; documented model identifier `gemini-4-hydrogen`, to be revalidated at integration time.
- Official Gemini API pricing (2026-11-17 check): https://ai.google.dev/gemini-api/docs/pricing . Hydrogen **Standard Free** input/output price displayed as free, **paid** $1.50/M input and $7.50/M output (including thinking tokens). Free-tier submissions may be used to improve Google's products; never send secrets, customer files, prompts or non-public materials.
- Rate limits https://ai.google.dev/gemini-api/docs/rate-limits : measured by RPM/TPM/RPD (and sometimes other quota), **per project**, not per key; RPD resets midnight Pacific time. Actual model/project/account quotas and available credit are **UNKNOWN** until authenticated AI Studio dashboard (https://aistudio.google.com/) reveals them; do NOT invent a per-day request count or assert $0 with a paid billing project.
- Gemini app free access != Gemini API unlimited/free quota. Any change to API eligibility, quota, Google ToS or pricing needs recheck. No API call, account connection, billing activation or key retrieval occurred during this design.

## 2. Explicit alternatives / best choice
| Mode | Benefits | Costs / shortcomings | Decision |
|---|---|---|---|
| Pure OFF | wholly offline, privacy, predictable 0 API spend | less novel candidate diversity | **Mandatory fully capable baseline** |
| Cloud as core reasoning | broad fluent answers | violates EAI independence, offline fail, leakage and quota risk | **REJECT** |
| ON for all input/answers | can be easy to implement | unconditional data transfer, model decides output, hidden costs | **REJECT** |
| **ON for selectively approved non-authoritative research** | alternate ideas, novel synthetic challenges, counterexamples, AXNODE candidate proposals; measurable improvement possible | quotas, privacy, more independent tests | **SELECT**, default OFF |
| AUTO/paid unrestricted fallback | may maximize throughput | surprise bills and unsafe implicit network egress | **REJECT**; any provider switch must be explicit |

**Core principle:** EAI can fully design, search, synthesize, verify and safely play in OFF mode. ON adds only untrusted proposal diversity and synthetic research; it must not become a silent dependency. ON may improve quality for some tasks but is NOT inherently more correct: independent benchmarks decide.

## 3. Stable ON/OFF modes and detachable provider interface
- `OFF` (**DEFAULT**): no Hydrogen import/initialization, network, key lookup, quota call, SDK dependency, model retrieval or external provider fallback. Local rule parser + optional installed loopback Qwen for INPUT classification + EAI CPU ProblemModeler/DesignEngine + AXNODE retrieval/synthesis + independent verifier + PolicyGate Player + local Episodes. Works with no internet, no API key, no local Qwen (deterministic limited fallback with explicit unsupported). Same DB/schema/AXNODE index, plan hash, result format in all modes.
- `RESEARCH_OPT_IN` (**ON**): first run exact OFF candidate/design path; then **only if** separately authorized outbound research payload and free-only project entitlement have been verified, generate an isolated minimal `ResearchPacket` with user-reviewed synthetic/public abstraction and explicitly allowlisted strategy IDs; Hydrogen may suggest `CandidateIdea` alternatives, synthetic test cases, counterexample hypotheses and critique. It NEVER returns trusted facts, executes tools, creates verified AXNODE, publishes results or approves actions. EAI independently typechecks, simulates and verifies proposals before admitting anything to candidate pool; final decisions/renderer and Player identical to OFF.
- `PAUSED_QUOTA` / `PAUSED_POLICY` / `UNAVAILABLE`: explicit, observable *status reasons*, not additional AI modes. No outgoing calls; continue OFF path, with stable checkpoint and ability to resume only after permitted quota/approval. Disabling ON cancels queued sends, drains in-flight response into quarantine/ignores late replies, leaves AXNODE and local result reusable.
- Proposed interfaces (DESIGN ONLY): `CandidateProvider.propose(ResearchPacket, QuotaBudget) -> CandidateIdea[]`, `NullProvider` pure OFF, `HydrogenResearchAdapter` isolated optional package with lazy loaded transport. Do NOT add cloud SDK to required Python dependencies. Policy-selected provider via explicit local settings; no dynamic arbitary URL, no model-invoked tool calls, no secret in logs.
- No automatic OFF→ON on uncertainty. No automatic paid upgrade. No remote fallback if local task fails. Offline result must not depend on prior remote output; remote-assisted candidates are provenance-tagged, never silently counted as EAI independently invented.

## 4. Strict boundary and schema contracts
`ResearchPacket v1`: nonce, local task family tag, approved synthetic/public-only short abstract (≤500 characters for v1), allowlisted public skill/AXNODE IDs and validation objectives, no raw user question, private identifiers, non-public repo content, credentials, customer data, stored episodes, raw retrieved web/document evidence, model weights, personal notes or unapproved context. Default DENY on doubtful classification. Require human-readable exact outbound preview and explicit per-send approval until a separate later narrowly scoped owner permission explicitly allows selected synthetic automated batches.
`CandidateIdea v1`: source=hydrogen, model_id, task_family, proposed typed DSL graph/reference IDs, assumptions, expected benefit, counterexamples, test hypotheses, local request receipt/provenance. Max response tokens and JSON byte limits; strict UTF-8, JSON duplicate-key check, no unknown keys, no code execution, no shell/sql arbitrary code, no unbounded loops or direct external actions.
`ProviderReceipt v1`: request hash (not raw prompt), approval hash/scope, provider/model, time, allowed policy, input/output usage if reported, latency, quota reason, response classification, safety status. Never store a raw private request. A response MAY be ignored while the OFF result remains usable. Provenance labels `LOCAL_INDEPENDENT`, `REMOTE_SUGGESTED_UNVERIFIED`, `REMOTE_SUGGESTED_EAI_VERIFIED` remain distinguishable; EAI verification does not erase remote origin.
Proposed settings (not currently supported):
```toml
[eai.cognition]
mode = "OFF"
local_qwen_input_only = true
[eai.research.hydrogen]
enabled = false
api_model = "gemini-4-hydrogen"
free_only = true
monthly_paid_budget_usd = 0
require_outbound_preview = true
max_requests_per_day_local = 5
max_input_tokens_per_request_local = 2048
max_output_tokens_per_request_local = 512
network_default_deny = true
```
Example ceilings are intentionally **local conservative safety settings, not official Hydrogen free tier limits**. CLI proposed `eai hydrogen status`, `eai hydrogen preview`, `eai hydrogen on`, `eai hydrogen off`, `eai hydrogen quota`; OFF is always usable even when status is UNKNOWN.

## 5. Zero-spend and quota gate (must fail closed)
1. Verify actual Google project/model eligibility and FREE pricing/tier in its authenticated AI Studio dashboard, ToS/privacy and billing state BEFORE any live request; record non-sensitive verification metadata/expiration locally. A code flag alone cannot prove Google will not charge; **if paid status or actual entitlement cannot be verified, block live calls**. This design does not guarantee a zero bill on an unknown billing account.
2. Hard configuration: paid API disabled and local budget $0; disallow paid Batch/Flex/priority/grounding or other billable tools. Do not attempt to auto-switch to paid if free exhausts. Even a different paid credential must not bypass this.
3. Enforce **minimum** of actual provider RPD/RPM/TPM limit (when known) and conservative locally configured ceilings; count reservations before request to avoid concurrent overruns, reconcile usage after response, cap payload/tokens and in-flight calls. Separate per-model & per-project counters to reflect project-level quota. Avoid assuming availability across midnight or reset date without source; display Pacific-based reset in UI if confirmed.
4. On HTTP `429 RESOURCE_EXHAUSTED`, 403, 401, network down, invalid response or uncertain tier: record safe diagnostic, open circuit breaker/cooldown as appropriate, suppress further calls and continue OFF; no storming retries, no credential guessing, no paid fallback. If result cannot be validated: quarantine candidate only, keep baseline output.
5. Remote access is opt-in and separately user-approved despite this DESIGN approval. Do not request keys, enable billing or change IAM in implementation stage without explicit consent. No tokens in GitHub, screenshots, traces, AXNODE text or error messages.

## 6. Architectural invariants when Hydrogen is ON
`EAI independently builds ProblemSpec, baseline DesignSpec/PlanSpec and verification obligations BEFORE reading any remote proposal.` ON can submit **only isolated research hypotheses**; never let a model write the final plan, final answer, approval hash, verifier receipt, user memories, AXNODE ACTIVE status or execution instructions. Proposed integration:
`LOCAL BASELINE → (optional external synthetic research proposal) → typed candidate pool → independent CPU constraints/solver → adversarial counterexample & proof gate → evidence-labelled best valid result → exact owner PolicyGate → Player.`
If Hydrogen suggests something better but independently verifiable, EAI may select it while recording its origin; this is **EAI-verified externally suggested** improvement, not autonomous EAI invention. Compare cases with the exact same EAI baseline to distinguish genuine quality gains from remote model answer laundering. Test output quality, failures and cost rather than claiming superiority.
No auto-feedback of remote output into the independent EAI memory/StrategyLearner without separate verifier and provenance. Verify learning transfer on genuinely new heldout families in OFF mode after any external-assisted training. If OFF regresses, revert model/AXNODE activation.

## 7. Benchmarks and acceptance
Run matched paired benchmarks with frozen seeds/cases/CPU budgets and exact EAI SHA:
- A: OFF core independent; B: ON with **recorded precomputed synthetic** Hydrogen proposals through fake transport; C (later only after consent): ON actual live Hydrogen on approved public/synthetic fixtures. A and B can be implemented/tested without API keys.
- Evaluate independent solved-task success, calibrated abstention, heldout/OOD transfer, verified novel AXNODE count, false verifier promotions, candidate origin, time P50/P95, CPU peak RSS, API token usage & remaining quota, number and type of outbound sends, billing tier evidence and denied leaks.
- Same test problems/acceptance for OFF and ON. OFF must pass without Internet, key, SDK or any remote cache. ON unavailable/429 gives the same safe baseline decision and receipt as OFF (plus non-sensitive fallback reason). Distinguish legitimate authorized research from external answer reliance.
- Test synthetic private prompt embedded in user requests, path traversal, prompt injection, 500+ char payload, forged JSON, unauthorized model ID, quota race, 429/401/503, late async response after OFF, re-entry, crash restore, preexisting 13 CPU solvers and P26 approvals. Verify outbound **0 bytes** in OFF via network spy.
- **Gates:** S0 offline mocks/proof, S1 consent/privacy/Google tier, S2 genuine model, S3 offline ablation and EAI independent outcome, S4 owner deployment/action. S1/S2 remain BLOCKED_APPROVAL/NOT_RUN in 2026-11-17 design.
- Hypothesis: ON may improve candidate coverage on some public synthetic tasks. Accept a live provider as a *quality-enhancing option* only when measured improvement outweighs latency/privacy/quota costs; otherwise OFF remains preferred.

## 8. Dependency and rollout plan
P0 **docs only** (this ADR + blueprint + queue, no runtime edits). P1 `NullProvider`/interfaces + opt-in settings and OFF regression/no-network spy. P2 fake `HydrogenResearchAdapter` with deterministic fixtures and failover/quotas/privacy filters. P3 independent validation/benchmark (OFF vs synthetic ON) with measured quality deltas. P4 only after separate owner approval and actual tier/PII/privacy review: live API adapter in isolated branch with no billing changes; synthetic outbound preview/consent. P5 native Windows + actual Qwen/Ollama, and final High acceptance; optional research facility never blocks EAI offline release.
No modifications to `my_local_ai`, HAE/LA, Vercel, main, existing P38 runtime/tests or customer data; existing draft PR and release hold preserved. Implementation completion & verification completion are distinct; new requirements are **DESIGNED_NOT_IMPLEMENTED**, `UNASSESSED` pending approved fixed weights.
