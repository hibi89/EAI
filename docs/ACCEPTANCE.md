# EAI acceptance gates and test matrix

## Gate S — source test (no network or model)

Command from repository root: python -m unittest discover -s tests -v
Additional: python -m compileall -q eai tests; python -m eai --version; python -m eai health.

Test targets: no paid services, synthetic conversation and restart memory, unauthorized freshness warning, mock online search + TTL reuse, failed retrieval warning, loopback URL enforcement, rejection of invalid questions/tool duplicates and bounded JSON parsing. These are **synthetic**, not proof of real Ollama or SearXNG operation. A manually reconstructed local source mirror (not byte-identical to GitHub) executed Python 3.13.5 compileall/CLI smoke and 15/15 unittests successfully on 2026-10-31 KST. Exact GitHub committed source CI conclusion remains unverified.

## Gate L — real local model (owner Windows only)

Prerequisite: Python 3.11+, Ollama installed and serving at 127.0.0.1:11434, model qwen2.5:3b downloaded. Verify CLI ask Korean answer; chat follow-up; process restart and persistence; missing model/stop server gives clear failure; CPU fallback can respond on older laptop. Measure RAM/time and retain minimal logs without personal text.

## Gate W — opt-in online retrieval

Prerequisite: local SearXNG and valid JSON search endpoint set by owner, explicit --online. Verify one live query returns correct provider source URLs, second same query consumes cache without new request, TTL expiration refreshes, offline or disabled provider returns warning, no access to remote/localhost arbitrary ports via an injected endpoint, no secret in query. A search hit must display as UNVERIFIED.

## Gate P — production/quality

Not applicable to local CLI until owner approves release/deployment. No Vercel project, domain, network-facing server or Production URL is created by this branch. Later, test backup/restore, system resource limits, workflow permissions, prompt injection and API rate limits before public exposure.

## Status rule

Code present != tests PASS. CI green != real Ollama PASS. A copied snippet != verified fact. A successful local smoke != production readiness. Record exact commit SHA, command, PASS/FAIL/SKIP and environment at every gate.
