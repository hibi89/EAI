# EAI V3.2 — P2 High-owned verification and defect repair acceptance (2026-11-19 KST)

**Scope:** `hibi89/EAI@feature/eai-v32-owner-rebuild-20261119`; do NOT substitute Astra's old SHA evidence. The frozen candidate SHA must be captured before integrated P2. **Execution owner: web GPT-6 High; independent technical/security and UX reviews still require separate actors.** No changes to main/Production, customer data, billing/credentials, real Hydrogen send or live Player authority.

## Gate entry

- All original `C01–C36`, six V3.1 FE obligations, and all twelve V3.2 owner UX SWUs have real code candidate paths tied to the *same* SHA.
- Existing mandatory CI and minimal immediate security protections remain active during P1. P2 starts only after the agreed P1 candidate; historic 48/48 Astra source-candidate coverage is not current confirmation.
- Freeze a concrete acceptance matrix, include failure probes, keep synthetic vs real OS evidence separate and prevent self-review from being recorded as independent.

## Original unchanged P2 requirements

Do not overwrite `docs/EAI_P2_VERIFICATION_QUEUE.json`. Preserve `EAI-P2-01..10`: complete compile/type/CI and 13 CPU baselines; isolated SQLite integrity, crash and restore; Architect constraint/unknown handling; independent forged-evidence/ACTIVE rejection; heldout learning and leakage; Player scope/idempotency/rollback; Hydrogen default OFF/free-only guarded mock and separate per-send live GO; actual Windows resource/CPU measurement; CLI/native UX; independent audit, High/owner GO. Existing Astra suite pass counts are retained as historical evidence against its specific source, not current PASS.

## Added V3.2 user workflow gates

| Gate | Acceptance | Evidence requirements | Initial state |
|---|---|---|---|
| EAI-V32-P2-UX01 | New clean user goal to genuine comparison or honest unsupported verdict | Real installed local CPU/AXNODE: goal → reviewed ProblemSpec → match → 2+ bounded alternative plans where viable → rejection reason → exact SHA; no fixtures mislabeled as AI output | NOT_RUN |
| EAI-V32-P2-UX02 | Approved pure Player path and rejected privilege escalation | Explicit selected plan digest/scope, pure simulated observed steps, interruption/changed-plan replay, independent trace vs digest verification, zero unauthorized external/DB/original effects | NOT_RUN |
| EAI-V32-P2-UX03 | Native Windows GUI and package UX | Clean Windows11 native EXE boot, real Korean IME, 125% scaling and minimum window, keyboard navigation, restart/history, deterministic export/error/cancel, portable extraction, source parity and SHA256 | NOT_RUN |
| EAI-V32-P2-UX04 | Offline & resource/privacy integrity across workflow | No socket traffic when Qwen/Hydrogen OFF, missing local parser graceful fallback, user-selected local files only, no secret logs, isolated DB backup/restore, actual cold/warm startup and RSS measured, full reproducible test/CI artifacts | NOT_RUN |

**Applicability:** browser/Playwright is NOT_APPLICABLE for a pure native Tk/Qt EXE unless an actual web surface is added; tests cannot be replaced by browser screenshots. P36 genuine local input classification remains BLOCKED if chosen model unavailable or abstaining; model-independent baseline must still pass.

## Defect and acceptance logic

- The High author runs exact-SHA full CI and local/Windows integration, labels each observation `PASS/FAIL/SKIP/NOT_RUN/BLOCKED`, patches code (not merely test expectations) and reruns. Full regression *after each code fix* requires new SHA and evidence.
- Existing Linux Xvfb combined Tk suite suffered a native Tcl/Python abort after 18 tests in the first 2026-11-19 attempt; a focused 9-test follow-up passed. Preserve this as an **unresolved flaky/OS-specific P2 item**, do not relabel as PASS.
- Validation percent = fixed accepted gates verified PASS only. There are 10 inherited P2 groups plus four new UX groups, but inherited content may contain many subacceptances; do not invent equal weights or official percentage. Until complete assessment: `verification_rate=UNASSESSED`, report gate count and exact SHA.
- User decides separately about operational permissions, paid network, GitHub writes, original data, active Player and commercial shipping. Independent audit is separate from author review and requires explicit independently run evidence, even though High is now the P2 implementation/test owner.
