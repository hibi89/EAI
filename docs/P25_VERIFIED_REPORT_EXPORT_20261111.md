# P25 — Verified offline customer report export (2026-11-11 KST)

## Design alternatives

- A: dump whole nested solver JSON into an interactive web dashboard. Fast to display, but can expose row values, excerpts and user-entered sensitive text, and adds browser/JS dependencies.
- B: execute only a user-explicit local typed goal/P12 batch/P14 pipeline with its existing independent receipt guard, **minimize report fields**, then output static CSP-restricted HTML or minimal JSON to stdout. Selected for offline portability and no customer-source leakage by default.

## Example

```powershell
python -m eai export-report examples/sample_batch_schedule.json --format html > my_eai_report.html
python -m eai export-report examples/sample_goal_batch.json --format json
```

Redirecting stdout to a new report is **the user's explicit choice**; the program never writes or overwrites a report file. It does not transmit or upload source material. The summary contains only manifest/goal filename and SHA256, bounded statuses, goal IDs/kinds, verification and limitations. It omits source cells, snippets, descriptions and internal solver detail. HTML escapes every input-derived string, contains no script or resources, and sets a CSP.

## Failure and authorization

Unsupported contract, changed goal/manifests, missing independently verified evidence and malformed source fail closed. Report SUCCESS does **not** guarantee the factual truth of the source, compliance or human authorization. No automatic repair, API, model call or external write. Entire normal solver/batch/pipeline execution still happens on the explicitly chosen input; source access remains subject to existing strict contracts. Production/Vercel N/A.

## Verification

Run `python -m compileall -q eai tests`, full Python3.11 unittest, CLI HTML/JSON tests. Native Windows, real customer file safety and browser printing are untested, so release remains HOLD.
