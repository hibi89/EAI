# P36 — Real localhost Qwen acceptance gate (2026-11-12 KST)

## Purpose and architecture
Keep the original CPU-owned, local-first EAI engine and 13 bounded goal types unchanged. Model input classification must never be mistaken for authorization, and fake Ollama replies must never be counted as a genuine model E2E pass.

Two approaches considered:
- A: silently start a model/download weights or call a remote API. This may incur runtime/API/download costs, export data, change local system state, and violate owner-approval boundaries; **rejected**.
- B: add a read-only, **explicit opt-in**, local-model acceptance harness with committed synthetic-only fixtures and an optional separately authorized synthetic CPU receipt. Zero external service/account dependency; no model installation or background request; **selected**.

## Implemented and tested
- `scripts/accept_local_qwen.py`: creates a brand-new temporary synthetic batch manifest with SHA-pinned `csv_key_coverage` and `schedule_tasks` examples. Uses only repository `examples/` fixtures and a synthetic natural-language request. Validates the exact `http://127.0.0.1:port`/localhost loopback URL, ASCII model ID and explicit `--ack-local-model`. Calls existing INPUT-only selector, requires the expected preapproved ID and `requires_explicit_execution=True`, checks fixture hashes for unexpected change.
- `--approve-synthetic-run` separately authorizes an offline, deterministic CPU goal execution using both pinned source SHA values and the existing independent receipt guard. Without this flag, model selection **never** runs the CPU goal.
- A missing/unresponsive model or ambiguous/unauthorized returned ID yields `BLOCKED` or `REJECTED`, never `PASS`. Status codes: 0 PASS, 2 REJECTED, 3 BLOCKED.
- `tests/test_local_qwen_acceptance_p36.py`: eight mock-based tests verify no implicit request, reject non-loopback endpoints, validate synthetic-only prompt, no automatic CPU execution, SHA-approved synthetic CPU receipt, wrong/unknown model choice, unavailable model, and default CLI block. These are **mocked** tests and not real Qwen validation.

## Executed source verification
- Exact feature+test SHA: `9e53920bd3df6cf8f0a89d3416905bf2045b9e9d`.
- [Actions #43200279491](https://github.com/hibi89/EAI/actions/runs/43200279491): Ubuntu Python3.11.18 **632 discovered / 631 PASS / 0 FAIL / 1 Windows-only SKIP**. Full existing original Python suite, syntax check, CLI smoke, deterministic synthetic offline candidate ZIP creation+verification, private candidate artifact upload all SUCCESS. Candidate ZIP SHA256 remains `6806459198a5214eae28cf95b7bc1000b275186a46d2df31e27b6875ace153b9`, artifact `13935096489`. Candidate packaging unchanged; receipt hash is not a signature.

## Actual model acceptance (NOT RUN in this environment)
Only on an owner-approved local machine with Ollama installed, a genuine local `qwen2.5:3b` (or explicitly chosen compatible model) already available, and no sensitive prompts or source files:
```powershell
python -m scripts.accept_local_qwen --ack-local-model
python -m scripts.accept_local_qwen --ack-local-model --approve-synthetic-run
```
Do **not** treat a `BLOCKED`/exit3 response as a pass. Results identify only the selected synthetic goal; the script does not send real source rows or customer prompts. Ollama remains a local process, external API calls from this script are not permitted by its URL contract. No application automation, external AI or customer disclosure approval is implied.

## Status and next acceptance
**Engineering 85% provisional retained; 95% NOT VERIFIED; RELEASE HOLD.** No actual Ollama/Qwen model inference, Windows 10/11 physical buyer acceptance, Defender/SmartScreen, consumer packaging license/rights, PII/retention policy, signing, customer pilot, or seller GO has been verified. Product `main`, original feature baseline, other repos and original customer files remain unchanged.

Next: native Windows 10/11 extracted candidate + CMD + HTML acceptance (currently one CI skip); genuine local Qwen invocation with above opt-in and independent result; customer privacy/rights/support verification. Do not inflate 85 to 95 based on mock tests.
