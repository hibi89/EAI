# EAI P15 — safe stdout-only batch/pipeline manifest creation (2026-11-10 KST)

## Problem and alternatives
P12/P14 currently require users to calculate exact goal JSON file hashes and type SHA256 manually. This is tedious and error-prone even with fully working solvers.
- A: Add editable UI / installer or autonomous filesystem writes. Higher complexity, needs user approval and raises unintended-write risk.
- B: Add a typed **read-only CLI** that constructs a pinned manifest entirely on stdout from explicitly selected local goal files. **Selected** for zero APIs, zero writes, existing validator reuse and low maintenance cost.

## Input, security and scope
`python -m eai make-manifest --mode batch --root examples --goal choose=sample_batch_choice.json --goal schedule=sample_batch_schedule.json`

For a dependency-gated pipeline:
`python -m eai make-manifest --mode pipeline --root examples --goal choose=sample_batch_choice.json --goal schedule=sample_batch_schedule.json --requires schedule=choose`

The output is a JSON object compatible with `batch-goals` or `pipeline-goals`, including actual SHA256 of exact file bytes and `continue_on_error`. To save a manifest, a user must explicitly redirect stdout to a local file; EAI itself never writes it. Optional `--stop-on-error` sets false. A root directory is explicitly scoped. Goal items must be existing files within it, <=64KiB, typed goal kinds from the existing registry. Paths, IDs and dependencies pass the same goal_batch/goal_pipeline validators, with duplicates, escape/symlink, invalid DAG, overly many goals (max six), unsupported kind and source mutation rejected before stdout success.

This does not prove an input fact is correct, does not execute the underlying goals, and does not perform any external lookups, model calls or authorized writes.

## Usage after explicit file save
In CMD (user-initiated redirect):
`python -m eai make-manifest --mode batch --root examples --goal choose=sample_batch_choice.json --goal schedule=sample_batch_schedule.json > examples/my_batch.json`
Then:
`python -m eai batch-goals examples/my_batch.json --json`

`python -m eai make-manifest --mode pipeline --root examples --goal choose=sample_batch_choice.json --goal schedule=sample_batch_schedule.json --requires schedule=choose > examples/my_pipeline.json`
Then:
`python -m eai pipeline-goals examples/my_pipeline.json --json`

Run full test suite: `python -m unittest discover -s tests -v`. Real Windows/PowerShell redirection, native packaging, live Qwen/Ollama, SearXNG and commercial use remain unverified until separately tested.
