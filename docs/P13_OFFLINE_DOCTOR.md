# EAI P13 — portable offline self-diagnostic (2026-11-10 KST)

## Alternatives
A. Display only Python/Ollama configuration (old health) — cheap but misses operational regressions and installation issues.
B. Test the four real typed CPU goal workflows, P12 batch fixture and SQLite in-memory while collecting per-check evidence. Chosen; no network/API/model calls, no user file or persistent database writes, no new third-party dependencies.

## Usage
python -m eai doctor --json
python -m eai doctor --root PATH_TO_EAI_FOLDER --json
RUN_EAI_DOCTOR.cmd (double-click from Windows repo root)

Reports Python version, coarse OS platform, 7 checks (Python >=3.11, SQLite :memory: query, choice, CSV audit, portfolio, schedule and goal batch), SHA256 of unchanged checked-in synthetic examples, expected domain status and guarded receipt PASS. A REVIEW/CONFLICT from a synthetically tested solver is not itself a diagnostic failure when it is valid and verified. Error detail is reduced to exception class; no prompts/home paths, tokens, or source content are uploaded.

Exit code 0 if all checks pass, 4 if any check fails. No claim that Linux CI tests Windows, real Ollama/Qwen, real SearXNG, user data, install packaging or release security. Owners should run this on actual Windows and share only the diagnostic result if requested.

Run tests: python -m compileall -q eai tests; python -m unittest discover -s tests -v.

## P13 hardening follow-up (implementation; CI unverified until executed)
- Local doctor now runs eight checks including the P14 DAG pipeline sample and requires the exact expected domain statuses (including a deliberately CONFLICTing CSV fixture), not merely a PASS receipt for any status.
- Two regression tests cover false-positive status acceptance and the pipeline smoke guard. Existing customer Windows, external model, and full source suite evidence are still separate gates.
