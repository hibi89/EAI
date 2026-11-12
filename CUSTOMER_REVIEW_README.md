# EAI Offline Customer Review — 0.1.0 beta (NOT A COMMERCIAL RELEASE)

This candidate contains source-only Python `eai.pyz`, synthetic CSV reference
fixtures, a Windows synthetic demo launcher and an unsigned SHA verifier.
It does NOT include customer data, a Python interpreter, Ollama/Qwen, weights,
credentials, n8n/HAE/LA source, installer, execution rights or paid services.

## First use (Windows 10/11, Python >=3.11)
1. Independently verify the ZIP against its adjacent `.sha256` using the
   repository-owned `scripts/verify_customer_candidate.py --archive ZIP --checksum ZIP.sha256`
   before extracting. This checksum is **not a digital signature**.
2. Extract the single `EAI-REVIEW-LOCAL/` folder into a new location.
3. Double-click `RUN_EAI_REVIEW.cmd`. It checks every extracted file against
   the embedded manifest and runs only a fabricated CSV demo into a NEW sibling
   folder `EAI-SYNTHETIC-REVIEW`. It opens its local HTML report.
4. Re-running the launcher refuses to overwrite existing output. Change any
   packaged file to see the preflight refuse execution.

For headless testing, use `RUN_EAI_REVIEW.cmd --ci` on Windows. No browser opens.

## Explicit local source review
Put an owner-authorized, already-sanitized supported goal JSON and its CSV
files together in a local folder. Use the existing EAI typed goal specification;
for example the packaged `samples/sample_key_coverage_goal.json` references two
matching synthetic CSV files. From the pristine candidate folder:

```powershell
python -I -B eai.pyz solve-goal samples/sample_key_coverage_goal.json --json
python -I -B eai.pyz customer-review --spec samples/sample_key_coverage_goal.json --output-dir ..\NEW-OWNER-REVIEW --ack-authorized-local
python -I -B eai.pyz verify-review --output-dir ..\NEW-OWNER-REVIEW
```

The output contains only `review.json` (minimized receipt), `review.html`
(local script-free report), `manifest.json` (unsigned hash consistency).
It never copies source CSV rows into the deliverable. Existing originals are
not modified. Nonzero conflict status in the report means human review is
needed, not success or authority to correct data. `--ack-authorized-local`
acknowledges owner choice, not authenticated legal consent.

## Limitations / gate
The two-file P31 referential check counts duplicate/empty master keys and
unresolved/blank detail references, with an explicitly chosen minimum match
percentage. It does NOT prove that matching keys are genuinely valid
relationships, and it cannot detect every source PII pattern or concurrent
file replacement race. No live model, human action automation, web upload,
user-device Windows acceptance, SmartScreen/Defender, commercial terms, customer
pilot, signed package, or legal provenance verification is included.
Keep RELEASE HOLD; do not resell or publish without separate owner approval.
