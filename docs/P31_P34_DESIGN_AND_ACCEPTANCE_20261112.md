# EAI P31–P34 engineering development and acceptance plan — 2026-11-12 KST

## Blueprint and comparative design
Original full EAI product goal remains private local-first independent CPU-owned planning, routing, verification and optional localhost Qwen input parsing. This work does not reduce that full target.
A. Modify original generic CSV reconciliation and publish raw joined keys for customer debugging: smaller patch, but possible key/data exposure, backwards-compatibility risk and poor independent proof.
B. Separate `csv_key_coverage` typed CPU goal and independently recomputed local receipt, then a source-free owner report and *separately versioned unsigned offline candidate*: extra small modules but safer contracts, low/no provider cost and better maintainability. Chosen B. No external API, model, original source mutation or release.

## Feature work plan
- P31 (+5 percentage points conditional): owner-chosen two CSVs with distinct, bounded relative paths; master unique nonempty keys, detail foreign key missing/blank counts, exact Decimal match threshold without rounding bypass, SHA before/after and independent DictReader/Counter re-evaluation; no key values or rows returned; explicitly preserve CONFLICT on any unreferenced key.
- P32 (+4pp conditional): `customer-review` and `verify-review` report/manifest. Explicit local owner acknowledgement, new folder only, CSP static HTML, minimal already-verified JSON, result verification, tamper/extra-file/missing-file and symlink/junction refusal, no raw data copies.
- P33 (+4pp conditional): existing source-only `.pyz` plus fixed synthetic samples, Windows demo launcher and detached SHA in separate reproducible ZIP with strictly allowlisted verifier. Not signed, not a native Windows installer, no actual customer or cloud transfer.
- P34 (+2pp conditional): separate process extract ZIP→real isolated zipapp→P31 source receipt→new report→integrity readback→negative duplicate/tamper/refusal, full original 582+ regression preserved. Windows native runner only if actual Windows CI/job runs; no claim without it.

## Gate and STOP/HOLD
Only score the increments after exact-source full GitHub Actions tests, executable ZIP build and synthetic journey PASS; these are weighted estimates of implemented engineering blueprint, not observed commercial readiness. No customer original processing in this chat, actual physical Windows10/11, real Qwen/Ollama, local permission proof, enterprise legal/PII review, signed binary, support policies, customer contract and sale remain OPEN. No GitHub branch merge or public deployment without separate review. Existing `feature/local-first-mvp` and `main` untouched.
