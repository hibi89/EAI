> **2026-11-17 owner design update (future only):** [ADR-0005 detachable Hydrogen OFF/ON](ADR-0005_HYDROGEN_DETACHABLE_DUAL_MODE_20261117.md) supersedes the future research-adapter *input-classification-only* restriction below solely to permit quarantined, untrusted synthetic/public **candidate suggestions and counterexamples** under explicit separately approved outbound preview. EAI retains planning/verification/final authority; existing P38 comparator, API blocked status, no paid/remote permissions and all historical evidence remain unchanged. This header does not authorize live API use.

# ADR-0004 — Optional Gemini 4 Hydrogen evaluation without surrendering EAI cognition
**2026-11-17 KST | Draft integration design; first offline benchmark implemented candidate**

## Authority and scope
User requested inclusion in EAI final blueprint and work to begin today. Original ADR-0002 remains canonical: local Qwen and any later Hydrogen adapter may only classify **INPUT** into allowed IDs. EAI CPU alone plans, executes bounded solvers, verifies receipts, decides and renders final output. EAI must remain usable offline with no API key, paid service or GPU upgrade. Model proposals never authorize GitHub writes, arbitrary tools, personal notes, raw file upload or a goal run.

Google officially announced Gemini 4 Hydrogen on 2026-11-12: https://deepmind.google/models/model-cards/gemini-4-hydrogen/ . Existence and API availability are verified; our account's API eligibility, free tier quota, model ID, future costs and actual performance are **NOT VERIFIED**. No API call, billing change or GitHub automation installation is approved by this ADR.

## Alternatives, performance/cost/maintenance
| Design | Benefit | Cost/risk | Decision |
|---|---|---|---|
| A. Hydrogen replaces EAI cognitive core and writes GitHub directly | broad language ability, flexible coding | violates ADR-0002, confidential data/permission/billing risks, vendor lock-in | REJECTED |
| B. Qwen-only local input parsing, EAI CPU independently reasons | offline, predictable, zero API | no Hydrogen benchmark/coding acceleration | BASELINE PRESERVED |
| C. External models as isolated candidate generators, offline evaluation first, separately approved optional connector later | measurable utility, opt-in, reversible, keeps CPU authority | adapter and data-minimization maintenance | SELECTED |

## Final architecture extension (without altering original 100%-scope)
1. User request -> deterministic EAI CPU parser, or approved local Qwen INPUT-only suggestion; explicit user approval before any remote provider use.
2. Future Hydrogen INPUT-only provider, when specifically approved, may receive **only intentionally supplied synthetic/non-sensitive <=500-character request plus allowlisted public IDs/kinds**. It must never receive customer files, .env, private GitHub source, chat history, database rows, retrieved evidence, authentication or unrestricted tool contracts. Default OFF, no automatic retry, zero-spend default, fail closed to CPU/manual review.
3. EAI CPU SHA-pinned manifest and goal hash validation -> CPU-owned solver, independent receipt verifier and deterministic rendering. Model outputs are untrusted proposals, cannot override ambiguity, grant permissions, choose unapproved IDs or bypass P26 owner approval.
4. Development-only Hydrogen GitHub worker: separate sandbox branch/PR, explicit GitHub App least-privilege scoped installation review, read-only first, no production or main merge. **Not configured or granted**. PR changes must be reviewed by the existing owner workflow.
5. The first deliverable is a pure offline benchmark from synthetic, precomputed responses; the script must never call Hydrogen/Qwen/Google/GitHub or modify project state. Counts only on stdout, no original prompts or raw outputs. Locally prepared fixture files not automatically uploaded.

## Requirements and acceptance
- EAI-H01: preserve ADR-0002 CPU ownership and current local CLI/13 typed-goal behavior; complete when no runtime changes and existing tests remain green.
- EAI-H02: owner-pinned SHA catalog, only exact allowlisted goal IDs, duplicate/malformed model JSON fail closed; prove with synthetic adversarial tests.
- EAI-H03: bounded 1–100 synthetic cases and <=400 offline predictions; compare CPU literal baseline and up to 4 models; output counts by correct/wrong/invalid/missing/abstain without prompt disclosure.
- EAI-H04: no network, external API, key, paid tier, secret persistence or GitHub write in benchmark; code review and offline socket denial test.
- EAI-H05: optional remote Hydrogen adapter only after separate explicit owner approval, account free-tier/price and ToS validation, data-scope audit; currently BLOCKED.
- EAI-H06: GitHub coding/review automation as separate permission-scoped proposal only; no installation/permissions change without owner GO; currently BLOCKED.
- EAI-H07: same synthetic benchmark for local Qwen, Hydrogen and CPU; report true models only after genuine executed tests. Fixture labels **are not live model evidence**.
- EAI-H08: product rollout requires real native Windows, genuine local Qwen, privacy, security, packaging, buyer rights and user final GO; RELEASE HOLD.

## Rollback and no-regression
The current EAI product branch is feature/kmong-eai-85-p31-20261112, not the historical feature/local-first-mvp. Original 13 typed goals, existing customer ZIP, workflow permissions, EAI main/other projects remain untouched. The benchmark lives in scripts/ only and is not imported into the EAI runtime. The official implementation and verification percentage remains UNASSESSED pending approved weights; legacy 85% is a historical provisional milestone, not an uplift from this design.

## Evidence types
- DESIGN: this ADR and task queue, commit SHA pending at authoring.
- IMPLEMENTED_UNVERIFIED: offline comparator and tests once committed, until exact SHA CI confirms results.
- NOT_RUN: actual Hydrogen API, genuine Qwen, native Windows, all production integration, privilege changes and customer data.
