# P30 — Portable end-to-end source-exact customer journey acceptance (2026-11-11 KST)

## Tested target

From the **real deterministic P27 zipapp** (not import-only helpers): explicit local CSV → P23 advisor → P15 SHA-pinned manifest → P24 CPU selection → P26 separate owner SHA approval → P19 independent CPU receipt → P25 static HTML summary. Also tests P28 one-command CSV and text analysis, P29 shifted cohort conflict, and opt-in Qwen input classification against an **in-process fake localhost HTTP server**. Only synthetic files are used.

No source file is modified by the application, no raw cell or secret marker is emitted by the advisor/HTML default, model request contains only owner request and allowlisted IDs/kinds, remote endpoint is not contacted and no selected goal is automatically executed. Wrong SHA blocks owner execution. The package is rebuilt twice and requires SHA256 identity.

## Security and accuracy limits

A fake Ollama response verifies the **HTTP/data boundary**, not an actual Qwen model's classification accuracy, latency, configuration or resource consumption. Linux Python3.11 packaging and subprocess E2E are not native Windows10/11, antivirus/SmartScreen or customer deployment proof. Real Windows/model and real customer tasks remain **UNVERIFIED**. This is engineering maturity evidence, **not retail release authorization**.

## Verification gate

Run `python -m unittest discover -s tests -v` on exact code/test GitHub SHA, check `compileall`, packed CLI execution, HTTP loopback boundaries, and CI conclusion SUCCESS before granting an additional milestone point.
