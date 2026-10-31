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
