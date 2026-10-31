# ADR-0003 — EAI adaptive CPU/GPU compute research (PROPOSAL, NOT IMPLEMENTED)
Date: 2026-10-31 KST. Owner requested investigating minimum GPU dependency and cooperative CPU/GPU use. STATUS: research candidate; **do not imply a fixed optimal split or approved runtime change**. ADR-0002 cognitive ownership takes precedence: Qwen is INPUT interpretation/classification only; EAI-owned code performs planning, solving, verification and output.

## Why
Owner's initial PC baseline (historical, remeasure locally): Windows 10; Intel Core i7-8750H (6C/12T); NVIDIA GTX 1050 Ti with 4 GB VRAM; system RAM 16 GB. A possible future desktop upgrade is **not a procurement requirement**. We need hardware-adaptive policies that allow ordinary CPU-only EAI tasks and graceful lower-end inference rather than an implicit large-GPU dependency.

## The real optimization problem
Do **not** choose a universal "70% CPU / 30% GPU" ratio. CPU utilization percentages and GPU utilization percentages are not interchangeable quantities. Split decisions depend on operation, memory bandwidth, batch size, token count, model quantization, physical CPU cores, available VRAM/RAM, KV cache, PCIe transfer cost, concurrency and thermal limits.

Hard constraints:
- validated IntentSpec/ResultSpec and independent EAI task-answer correctness must not deteriorate;
- user-defined device VRAM/RAM ceilings, no process crash/OOM, no network/external paid API;
- default protected CPU/thermal budget so the host remains usable, no intrusive driver/power/policy changes;
- experimental model runs do not upload private prompts or model/data files to GitHub.

Optimize on **task-specific feasible Pareto frontier**: p50/p95 end-to-end latency, Qwen parse accuracy, EAI solver correctness, peak VRAM, peak resident RAM, CPU load, optional measured energy and model-switch overhead. Do not invent watt/energy numbers when power telemetry is unsupported. The proposed selection score is configurable and valid only within measured task/hardware conditions. Favor lower GPU footprint if latency/quality remain acceptable; otherwise select a faster GPU-offload profile, with an explicit CPU-only fallback.

## Workload partition
| Stage | Default device | Acceleration condition |
| --- | --- | --- |
| Text/rule preclassifier, schema validation | CPU | never require GPU |
| Qwen structured intent parse | CPU baseline | optionally limited/all GPU offload if validated/benchmarked; Qwen produces only IntentSpec |
| Workflow scheduler, graph search control, retries, evidence/SQLite, HTTP, hashes | CPU | never require GPU |
| Deterministic numeric solver / constraint propagation | CPU | GPU only for a measured parallel numeric kernel |
| Vector/embedding retrieval | CPU baseline or separate embedding engine | consider optional GPU only if query throughput/latency justifies memory |
| Later ML strategy router | CPU baseline | conditional on benchmark |
| Future large tensor batch solver | CPU or GPU depending on kernel | hardware- and task-specific |

## Alternatives compared
A. **Static hardware profiles (recommended FIRST):** CPU_ECO, HYBRID_BALANCED, GPU_FAST with explicit memory/threads/context/offload settings, conservative defaults and manual override. Low complexity; reproducible; no quality regression via dynamic switching; initial EAI engine remains entirely CPU-run except optional Qwen parser acceleration.
B. **Adaptive compute scheduler (research LATER):** measure per task/model/device, maintain calibrated profiles, choose before each job with VRAM reserve, latency/deadline and thermal guard; hysteresis to avoid frequent reload; rollback to last verified profile. Better potential utilization but calibration, observability, debugging and model-reload churn increase complexity. Requires proof it beats A on held-out task traces and user-usefulness.

Decision status: A is recommended staging method but **not yet implemented**. B is a proposed long-term enhancement, not a requirement for v0.1 completion and not approved to replace the running backend automatically.

## Bench protocol (local opt-in, proposed)
1. Inventory CPU model/core count, available RAM, GPU model/VRAM, OS, model/version/quantization, Ollama/llama.cpp version, backend. Record only safe hardware identifiers and hashed representative prompt IDs.
2. Define deterministic Qwen IntentSpec benchmark set: short/long requests, Korean/English, ambiguity, no-model-rule fallback, and fixed structured parsing accuracy. Define separate original EAI solver task set (calculations, small workflow planning, evidence verification) independent of model inference.
3. Establish CPU-only baseline with same task data. Run warm and cold requests separately. For the Qwen parser only, compare model quantizations (license checked), context lengths, CPU thread counts (e.g. 1/2/4/physical core count within machine limit), and measured GPU-layer offload options 0 / partial / full *when supported*. One profile per trial; no auto power tuning.
4. For each supported profile: warmups then repeated trials (minimum 5 repeats in experiment design), order shuffled when feasible, log p50/p95 end-to-end, prompt and decode duration/tokens if exposed, parser validity/accuracy, CPU/RAM/VRAM, temperature when supported, and errors. Throttle/thermal state and concurrent background loads must be recorded. Drop dangerous/OOM candidates.
5. Compare CPU_ECO vs HYBRID_BALANCED vs GPU_FAST on the **same** tasks. Select a nondominated safe profile per workload and available resource budget. Differences must exceed run-to-run noise; otherwise keep simpler CPU/default profile.
6. Validate on held-out tasks and a Windows owner session. Benchmark data must not be committed if it contains content, personal information, secrets or large raw logs. Only anonymized aggregate metrics and reproducible scripts may be committed.
7. Later introduce adaptive scheduler behind disabled-by-default feature flag, add regression tests for low VRAM, no GPU, GPU busy/unavailable, thermal pressure, memory pressure, prompt injection and failed profile switch; rollback to known safe configuration.

## Native capabilities and constraints (official research, verified 2026-10-31)
- llama.cpp documents hybrid CPU/GPU inference and partial model-layer GPU offload: https://github.com/ggml-org/llama.cpp
- Current llama-bench documents -ngl/--n-gpu-layers, -t/--threads, prompt processing and token-generation benchmarks with CSV/JSON output: https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md
- Ollama API documents per-request 'options' such as num_gpu, num_thread, num_ctx and response durations/counters: https://github.com/ollama/ollama/blob/main/docs/api.md
- Ollama FAQ warns parallel request/context settings increase RAM/VRAM and that placing a model entirely on one GPU often avoids bus transfers: https://github.com/ollama/ollama/blob/main/docs/faq.mdx

Capabilities do not imply identical behavior across backend versions, drivers or GPU types. Verify installed version before choosing an argument. The exact 'golden ratio' has **not been measured**.

## Minimum tasks and acceptance
- First, implement ADR-0002 IntentPort / EAI CognitiveEngine / ResultSpec / deterministic renderer, so Qwen-only classifier behavior can be objectively tested.
- Add read-only benchmark/profiling script for Qwen parser CPU-only (and optionally GPU offload) with NO service reconfiguration, NO privileged process, NO input data uploads; approve separately before the local hardware experiment.
- Offline tests: scheduler selects CPU when no GPU or telemetry missing, rejects oversubscribed memory, preserves output schema, and never causes model to synthesize final answers.
- Real hardware test: collect reproducible results on owner's actual PC when available; do not claim measurements from mock data.
- Promotion gate: adaptivity must improve a defined objective without reducing task quality or increasing crashes versus static profile.

## No changes executed by this research note
No backend code edits, no hardware benchmarks, no model downloads, no LA/HAE edits, no OS/driver modifications and no new paid services. This is an R&D specification only.
