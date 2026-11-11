# P24 — CPU-owned SHA-pinned goal selector (2026-11-11 KST)

## Alternatives

- A: let Qwen translate a user request into arbitrary tools and execute automatically. Flexible but model hallucination or injected instructions could authorize data reads or writes.
- B: restrict selection to owner-created SHA-pinned **existing** P12/P14 goal manifests, use exact CPU identifier matches first, optionally ask local Qwen to classify the request to **one of those identifiers only**. Always require an explicit separate `solve-goal` invocation. Selected for bounded auditability and zero recurring cost.

## Usage

```powershell
python -m eai select-goal --manifest examples/sample_goal_batch.json --request "schedule" --json
python -m eai select-goal --manifest examples/sample_goal_batch.json --request "schedule" --json --qwen-select
```

Default is CPU-only and never calls the model. Model mode (with --qwen-select) connects strictly to loopback HTTP Ollama, sends only the user request plus allowlisted IDs and kind labels, **not local goal JSON, datasets or documents**. It uses structured output and rejects unknown IDs, duplicate JSON keys, invalid shape, unavailable model, bad URL and changed SHA. A selected candidate is not executable authority. The user must inspect it and separately execute `solve-goal`.

Supports 1–6 existing owner-pinned goal_batch or goal_pipeline entries. Checks manifest SHA and all selected goal SHA values before and after potential model calls. No implicit files, auto network, cloud, shell, writes or unbounded retries.

## Verification / limits

New tests include CPU exact/ambiguous routing, fake local Ollama, unknown/malformed model output, remote URL rejection, TOCTOU manifest mutation, symlink protection, CLI exit status and zero writes. GitHub Python3.11 full regression and exact SHA required for acceptance. Real Qwen, native Windows and customer workflows remain untested; release HOLD. No claim of general semantic understanding.
