# P35 — Canonical customer candidate ZIP security gate (2026-11-12 KST)

## Goal and choice
Strengthen the separately packaged, **unsigned** EAI offline-review ZIP without changing the source-only EAI engine, owner data, release permissions or original 13 CPU goals.

- Option A: keep allowlist, member SHA and detached hash only. Low CPU cost but Python `zipfile` accepts an EXE-like prefix, undeclared trailing bytes and ZIP comments while still exposing exactly the same allowed members. An attacker can recompute an **unsigned** detached checksum; this is an unaccounted-content and buyer review risk.
- Option B (chosen): reconstruct the precisely-defined, deterministic ZIP byte layout from its manifest-validated members and reject any byte mismatch. Memory/CPU bounded by the existing 6,291,456-byte outer archive cap; no new dependencies, external requests or licensing assumptions. Builder remains unchanged.

## Implementation
- `scripts/verify_customer_candidate.py`: after existing fixed inventory, non-encrypted stored-entry and source SHA verification, serialize the producer's exact ordered ZIP metadata and member bytes; reject a differing original with `ARCHIVE_NONCANONICAL`.
- `tests/test_customer_candidate_p33.py`: actual `zipfile` acceptance followed by hard refusal for three independently tampered files: prefixed `MZ`/self-extracting style, undeclared suffix and opaque archive comment. Existing good candidate, extracted package, CLI, source-free report and tamper tests retained.
- Still **unsigned**: this check proves exact format, **not** author identity, malware freedom, trustworthy download origin or buyer rights.

## Executed verification and remaining gates
- Exact GitHub source+test commit: `fe5b3d56ea79b50ac80aa4d0cb3df564c400243d`.
- [GitHub Actions #43198255549](https://github.com/hibi89/EAI/actions/runs/43198255549) **SUCCESS** on Ubuntu Python 3.11.18; `python -m unittest discover -s tests -v` **624 total / 623 PASS / 0 FAIL / 1 Windows-only SKIP**, syntax, original CLI, actual deterministic customer candidate build+verification, private artifact upload all PASS.
- New exact synthetic candidate ZIP SHA-256 `6806459198a5214eae28cf95b7bc1000b275186a46d2df31e27b6875ace153b9`; private Actions artifact ID `13932949816` (temporary review evidence, not sales release).
- Native Windows 10/11 consumer hardware, Windows `.cmd` execution, physical Defender/SmartScreen, genuine localhost Qwen, approved customer file rights/privacy, licensing, customer QA and retail owner approval: **NOT VERIFIED**. GitHub Windows hosted runner was **not** newly requested.
- **Engineering completion remains 85% provisional; P95 NOT ACHIEVED; RELEASE HOLD.** Improved hardening is not by itself proof of new 10 percentage-point product scope.

## Safe continuation
1. Use an approved Windows test environment to run extracted `RUN_EAI_REVIEW.cmd --ci`, verify the exact candidate SHA, actual file:// HTML and path/locale behavior.
2. With explicit local-model and owner-approved data scope, verify genuine Qwen **INPUT-only** goal classification, SHA-pinned explicit execution and CPU receipt consistency. Never transmit raw data to remote AI.
3. Perform controlled privacy/rights review, independent buyer use, delivery/support license and release authorization. Keep original `main` and `feature/local-first-mvp` untouched until separate merge approval.

**Verified status at 2026-11-12 KST:** source SHA above and GitHub-hosted Ubuntu job; no Vercel/Production application.
