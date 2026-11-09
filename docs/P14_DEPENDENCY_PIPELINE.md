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
