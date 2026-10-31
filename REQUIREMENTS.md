# EAI REQUIREMENTS — P8, 2026-10-31 KST

## Goal and boundary
Independent EAI for local daily use: optional Qwen strictly parses/classifies user INPUT. EAI-owned CPU code plans bounded tasks, computes, selects, validates and renders outputs. GPT-level all-domain cognition, original language model training and universal agent capability remain unproven future research.

## Implemented
- P0: strict intent, local CPU arithmetic, optional opt-in localhost search, SQLite history/cache.
- P1: explicitly authorized local notes, recall, and pre-migration SQLite backup.
- P2: Decimal comparison and bounded read-only CSV profile.
- P3: claim-vs-CSV numerical verification and hash-backed result.
- P4: keyed two-file reconciliation and evidence checks.
- P5: multi-metric discrepancy diagnosis with bounded candidate hypotheses, not causal attribution.
- P6: fixed goal planner for CSV audit, read-only fallback/escalation, hash verification.
- P7: two strict local JSON goal kinds, choose_options (weighted score, hard limits, Pareto) and csv_audit.
- P8: independent receipt guard rechecks original constraints, scoring, Pareto winners, CSV file hashes, route strategy, status and allowlisted steps; returns bounded advisory details, fails closed on forged/inconsistent receipts.

## Nonfunctional requirements
Python >=3.11 standard library, CPU-first, no paid API/GPU required for deterministic tasks, user-private files never uploaded, no unapproved file modifications, no default listener, no arbitrary code execution or self-changing goal constraints. Only explicit --online search may relay queries through local SearXNG. No HAE/LA/main changes. New billing, permissions, model training, sensitive external transfer, autonomous writes or public deployment require owner approval.

## Gates
Linux Python 3.13.5 local mirror: 201 PASS, 0 FAIL, including 21 P8. Three P8 blobs exactly match GitHub; full byte-identical checkout tests are not proven. GitHub Actions runner pre-step failure persists, real Windows Python 3.11 and Ollama/SearXNG unverified; no Vercel Production target.
