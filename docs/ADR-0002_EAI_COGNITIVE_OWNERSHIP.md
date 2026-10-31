# ADR-0002 — EAI owns intelligence; Qwen is ONLY the language intake adapter
Date: 2026-10-31 KST. Decision status: OWNER CLARIFIED FINAL TARGET. Supersedes ADR-0001 wherever it assigns question answering, solution synthesis, planning, judging or conclusions to Qwen.

## Owner intent
EAI is an independently developed agent/intelligence system that must eventually compete on useful task-solving ability with GPT-class assistants. Qwen is solely a subordinate natural-language *input interpretation and classification* model. Existing EAI code that lets Ollama/Qwen generate final answers is a provisional, incorrect architectural baseline, NOT the approved final model.

## Strict ownership / data flow
User text -> Qwen adapter (text-to-validated IntentSpec only) -> EAI Cognition Core -> independent problem/goal graph -> EAI planner, memory, reusable tool registry, search/workflow executor, verifiers, deterministic solvers -> EAI ResultSpec with evidence/conflicts/uncertainty -> EAI response renderer -> user.
All reasoning, choice of tools, plan revisions, verification decisions, state and response authority belongs to EAI. Qwen outputs are untrusted proposals; Python schemas, validation and permission gates reject or ask for clarification on malformed, dangerous or ambiguous intents. Qwen must not be called with retrieved evidence for answer generation. Qwen must not invent the solution, execute actions, approve its own plan, determine truth or train itself.

## Architectural alternatives reviewed
- A: Qwen parses + synthesizes answers; independent EAI tools only assist it. Fast general chatbot with good fluency, but violates owner objective and prevents evaluating EAI intelligence separately. **Rejected as final architecture.**
- B: Qwen parses only; EAI's own deterministic + algorithmic reasoning/verification system chooses and computes results, with a separately implemented structured response renderer. Slower to build broad conversational coverage, but true ownership, testability, provenance and extensibility. **Selected final target.**

## Important feasibility boundary
An orchestrator plus search and rules is *not* a GPT-class language model. GPT-class broad conversation, flexible abstraction and natural language generation without any general generative model would require substantial new model architecture, training data, compute and empirical evaluation. No performance equivalence is promised. In the first runnable version, narrow verifiable tasks receive complete, deterministic structured answers; unsupported open-ended requests return an explicit limitation, NOT a secretly Qwen-written answer. Expansion toward general ability is a separate multi-stage research effort.
A separately approved, optional language renderer could later be investigated, but must be isolated from reasoning and may not silently replace the EAI-own-generation research goal.

## Three-part core, developed incrementally
1. **IntentPort (first):** Qwen => versioned IntentSpec {task_kind, goal, constraints, time_scope, entities, data_needs, confidence/unknowns}, then strict local validation. Rule-based fallback for known intents if Qwen is unavailable; never use Qwen to write final answers.
2. **CognitiveEngine (first):** own code constructs ProblemSpec and TaskGraph, selects pre-registered solvers/workflows, executes with time and resource limits, reconciles evidence, produces ResultSpec {status, claims, calculations, sources, uncertainty, plan_trace}. Prove on a small domain before generalization.
3. **ResponseEngine (first):** renders ResultSpec to Korean/English using deterministic templates and references, not a model-produced arbitrary answer. Over time, evaluate separately designed local NLG capabilities; do not pretend early templates equal GPT.

## Research ladder (long-term, no fixed success guarantee)
- V0: EAI-owned task routing + one end-to-end deterministic solution; Qwen only structured intake; local memory; CLI; tests.
- V1: multi-solver verification, caching/source provenance, reusable workflows, structured feedback learning.
- V2: hierarchical search and bounded parallel solvers; measured improvements over plain search and one-step deterministic baseline.
- V3: independent strategy learning/ML routing trained on lawful execution outcomes; held-out success and latency evaluation.
- V4+: explore original generalized reasoning and original answer generation research only if justified by task benchmarks and available compute/resources.

## Executable proofs required
- Test that Qwen response is only JSON-shaped IntentSpec; any response outside schema is rejected.
- Test that Qwen is never called to synthesize final answers, and receives no fetched document content for solution synthesis.
- Test that EAI independently selects tools, executes deterministic solvers, checks evidence and produces ResultSpec without Qwen except for parsing (using fake parsed intent).
- Test online denial, prompt injection, budget/timeouts, stale data and unverified evidence handling.
- Measure EAI independent task accuracy against a no-reasoning baseline and the existing Qwen-only chatbot as a reference; report actual quality, not GPT equivalence.

## Migration note and source gap (2026-10-31)
Current eai/app.py calls self.model.respond(messages) to generate final text, and eai/providers.py implements OllamaChat.respond. Those files were inspected read-only. The code and earlier synthetic tests remain on the feature branch and are explicitly **NOT COMPLIANT** with ADR-0002. Replace only after writing typed contracts and no-regression tests; avoid conflating first working code with the new final architecture.
No changes to HAE, LA, Qwen model weights, external services, data or deployment are authorized by this ADR.
