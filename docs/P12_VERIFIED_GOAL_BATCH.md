# EAI P12 — verified local goal batching (2026-11-10 KST)

## Alternatives
A. Shell loop invoking a process per goal: simple but weak input provenance, process overhead, messy error handling and duplicate-launch risks.
B. In-process sequence through existing bounded offline goal dispatcher: explicit checksum preflight, safety, individual validation, and failure isolation. Chosen. No external model, network, database writes or added dependencies.

## Contract
Strict JSON: version=1, kind=goal_batch, continue_on_error boolean, items array of 1-6 entries. Each has id, relative goal, lowercase SHA256 of goal bytes. Manifest and each goal <=64KiB. Rejects duplicates, symlinks escaping directory, self-reference, absolute/parent traversal, unknown fields and Windows drive paths. All hashes preflighted before ANY child execution. Each child uses existing independently verified four CPU domain solvers. No automatic retry. Continue-on-error isolates invalid child; otherwise later goals are SKIPPED. Final manifest and all input hashes are rechecked.

Aggregate COMPLETE (all DECIDED or AGREE), REVIEW (unresolved but validated TIE/CONFLICT/UNAVAILABLE), PARTIAL (valid results plus errors), FAILED (no successful result). Envelope receipt checks goal IDs/order/checksums, independent goal guard PASS evidence, aggregate counts and stopping policy; it does not independently rerun each child solver. Success never asserts real-world work completed. Outputs only stdout; no files modified by EAI.

## Run
python -m eai batch-goals examples/sample_goal_batch.json --json

CLI exit code: 0 COMPLETE, 2 REVIEW, 3 PARTIAL, 1 FAILED or invalid manifest.
Test: python -m compileall -q eai tests && python -m unittest discover -s tests -v

## Not verified
Windows10 native hardware, real local Ollama/Qwen, live search, actual customer source, commercial distribution. All require separate evidence.
