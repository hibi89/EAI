# P37 — Native Windows customer candidate acceptance harness (2026-11-12 KST)

## Goal and safe design
The P33 real Windows `cmd.exe` test had been skipped in Ubuntu-only CI. EAI cannot honestly call its customer-runner Windows-verified without actual Windows execution. Keep 13 CPU goal kinds, P35 canonical ZIP verification, P36 local Qwen boundary, source data and repository baseline unchanged.

Two approaches:
- **A. Automatically add GitHub-hosted Windows runner to every PR.** Direct runner proof if successful, but private-repository Windows runner minutes may consume included or billable quota; quota/payment authority not verified. Not applied without budget confirmation.
- **B. Explicit local-host synthetic acceptance harness**, then bind it to the existing native-only test. Requires no new paid service, no automatic GitHub Windows jobs, no real customer data, no model, no new installations. **Selected.**

## Implementation / what the acceptance checks
`scripts/accept_windows_candidate.py`: requires `--ack-windows-host`; denies non-Windows with `BLOCKED/NATIVE_WINDOWS_NOT_AVAILABLE`; builds the existing deterministic source-only candidate in a temporary directory containing Korean characters and spaces; independently validates ZIP and checksum; extracts to a brand-new folder and verifies the complete fixed inventory; invokes real `cmd.exe /d /c RUN_EAI_REVIEW.cmd --ci` (70-second cap); checks `review.json`, CSP-bearing static HTML and minimized source values; repeats the CMD and requires exit 2 without overwriting output; re-hashes all extracted input files; deletes synthetic temporary data on completion. Output is a minimal JSON PASS/BLOCKED/REJECTED evidence statement with original-user-data flag and `release_approved=false`.

`tests/test_windows_candidate_p37.py`: five Linux-compatible fail-closed/invariant tests. The existing **single** `@skipUnless(os.name == 'nt')` test in `tests/test_customer_candidate_p33.py` now also runs the full P37 Korean-path acceptance **only when a real Windows host is available**. CI on Ubuntu still skips exactly one native test.

## Exact evidence
- Feature code+test SHA **`f3a61e624e5d21a21700ec21930a9021b4acd9c2`**, including the native-only wiring.
- [GitHub Actions #43202624144](https://github.com/hibi89/EAI/actions/runs/43202624144) Ubuntu Python3.11 **637 total / 636 PASS / 0 FAIL / 1 Windows-only SKIP**, syntax check, full existing CPU goals, CLI, actual portable synthetic ZIP creation and independent verifier, private artifact upload all SUCCESS.
- P37 prior intermediate SHA `6e0e994baa7743bf2951e538322753a4b7b306ca` also passed [Actions #43202375006](https://github.com/hibi89/EAI/actions/runs/43202375006) with the same 637 / 636 PASS / 1 Windows SKIP, before the P33 native-only wiring.
- Synthetic ZIP bytes unchanged from P35/P36: SHA-256 `6806459198a5214eae28cf95b7bc1000b275186a46d2df31e27b6875ace153b9`; final temporary private artifact ID `13934909841`. This is **unsigned**, not sales merchandise.

## How to get *genuine* Windows proof (not yet done)
On an authorized Windows 10/11 or Windows runner with Python 3.11+ already installed, from the checked-out exact SHA:
```powershell
python -m scripts.accept_windows_candidate --ack-windows-host
python -m unittest tests.test_customer_candidate_p33 -v
```
Record the PASS JSON and actual host/OS/Python version for that exact SHA. This script does not check Defender/SmartScreen malware acceptance, binary signing, rights, installation without Python, or real buyer acceptance. It is a synthetic CMD acceptance only; a Windows Server CI pass would **not** certify consumer Windows 10/11.

## Status / delivery
**EAI whole-product engineering 85% provisional remains unchanged; P95 NOT CERTIFIED; RELEASE HOLD.** True native Windows CMD acceptance, genuine local Qwen inference, customer rights/privacy/legal/signing/support, pilot and owner sale approval remain UNVERIFIED. Original `main`, base branch `feature/local-first-mvp`, secrets and customer data untouched. GitHub test SHA above provides source rollback; no Vercel/Production applies.
