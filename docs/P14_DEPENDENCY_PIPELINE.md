# EAI P14 — versioned dependency-gated offline goal pipeline

2026-11-10 KST

## Alternatives
A. Manual P12 batch execution with externally ordered scripts: quick but risks running dependents after a prior unapproved or failed result.
B. Strict 6-node DAG of SHA256 pinned typed goals, topological order, evidence-based dependency gates, and independent envelope verification: chosen for determinism/security with negligible local CPU overhead.

## Contract
JSON manifest version 1, kind goal_pipeline, continue_on_error boolean, items 1-6. Each item explicitly requires id, relative goal file, exact SHA256 and requires list of predecessor IDs. All referenced goals and manifest are <=64KiB. Unknown/self/cyclic/duplicate dependencies rejected before any execution. Input paths+hashes use P12's path sanitizer and SHA preflight. Each goal uses the real P7-P11 dispatcher and receipt verifier; no model execution, networking, auto retry, writes or payments.

Ready independent nodes execute in deterministic sorted order. A dependent node only executes when all direct predecessors returned a guarded DECIDED or AGREE. TIE/CONFLICT/UNAVAILABLE and any child ERROR cause dependent SKIPPED, with explicit blocked_by names. continue_on_error=false stops remaining nodes after an ERROR, while review statuses gate dependent nodes but do not cancel independent work. Envelope guard recomputes allowed order, dependency gates, provenance, child PASS flags, stop rules and aggregate counts. It does not re-run the underlying goal math. COMPLETE/REVIEW/PARTIAL/FAILED mean bounded evaluation status, never autonomous completion of real work.

CLI: python -m eai pipeline-goals examples/sample_goal_pipeline.json --json.
Exit 0 COMPLETE, 2 REVIEW, 3 PARTIAL, 1 FAILED or invalid manifest.

Unit/CLI validation: python -m unittest discover -s tests -v; python -m compileall -q eai tests.

Open gates: real Windows, Ollama/Qwen intent parser, customer workload, continuous task orchestration, commercial distribution, external service permissions and actual project completion.

## P14 receipt integrity follow-up (implementation; CI unverified until executed)
- In-pipeline verification binds manifest SHA256 to the original bytes and separately rechecks canonical topological execution order; forged digest, swapped independent order and unhashable order records are fail-closed.
- The external optional postcondition helper accepts an expected SHA256 when original bytes are available; do not assert a SHA binding from a bare caller-supplied manifest object alone.

## GitHub exact-source acceptance (2026-11-10 KST)

- Code/test SHA `bbd01576eed2573ffeab5a70eec0662fcb40bad0`: [Actions 42675220982](https://github.com/hibi89/EAI/actions/runs/42675220982) Linux Python3.11 301/301 PASS, Syntax check + CLI smoke PASS.
- P14 rejects an unpinned original manifest SHA mismatch and reorders under an independent canonical dependency pass in the receipt verifier. Test module **18 tests PASS** including forged output and dependency holds.
- Original input data and customer Windows are NOT VERIFIED; no model/remote tool calls or automated real task execution.
