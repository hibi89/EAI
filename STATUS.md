# STATUS — EAI P3 (2026-10-31 KST)

## Canonical state
Private hibi89/EAI, development branch feature/local-first-mvp, main preserved. P3 source milestone **c108648b0e153b8252e8ff0faf715518a75d4440**. EAI independently performs CPU calculation, lookup, explicit local note storage, CSV statistics and claim verification. Qwen may **only classify input**; no model writes the final answer. Broad GPT-class generality/ML/adaptive GPU split remain research, not implemented. HAE/LA/SOVIA unaffected.

## Delivered
- P0: rule parser + optional Qwen IntentSpec-only port, exact arithmetic, opt-in local SearXNG lookup, SQLite history/cache.
- P1: literal opt-in notes and local search, legacy SQLite backup prior to notes migration.
- P2: bounded Decimal comparison and explicitly selected read-only CSV numeric profile.
- **P3:** read-only \`verify-csv\`, 1 or up to 24 JSON claims, SHA256 before and after reading, per-claim VERIFIED/CONFLICT/UNAVAILABLE, actual vs asserted number, tolerance, exit codes 0/1/2/3 and machine-readable JSON; no external calls or model.
- No frontend/hosted server/LA integration/weights training.

## Tests and integrity
- Local Linux Python 3.13: \`compileall\` PASS and \`unittest discover -s tests -v\` **74 PASS / 0 FAIL / 0 SKIP**, 19 new P3 tests. Real CLI success/mismatch/unknown column and batch sample PASS. Source CSV unchanged.
- GitHub readback confirms the **four P3 changed/new source files match local Git Blob SHA**. Whole byte-identical remote checkout tests still UNVERIFIED due older mirror formatting differences.
- GitHub Actions P3 source run **41203228592 FAILURE**, zero job steps, empty runner name, ~2 seconds from start to completion. Previous 15 runs showed similar pre-step failure. Root cause UNKNOWN, neither a proven code error nor CI success. Stop repeated no-op reruns; only inspect effective logs/config with authorized access.

## Outstanding
Windows 10 Python 3.11 owner's actual PC, real Ollama/Qwen, SearXNG, CPU/GPU benchmarking: UNVERIFIED. Vercel Production: NOT APPLICABLE to local CLI. No existing originals or user data changed. No paid API or externally transferred personal content.

## Next
1. Verify byte-identical remote checkout/Windows Python 3.11 and P3 real CLI as soon as the actual runtime is accessible; preserve user CSV originals.
2. Diagnose GitHub Actions pre-step failure only from actionable runner/permission evidence; no unauthorized account changes.
3. Expand one independent solver based on user work (group claims/typed units/provenance), keeping CPU-first design and small verified increments.

Document details: docs/P3_CSV_CLAIM_VERIFICATION.md. GitHub HEAD after documentation commit must be verified; P3 source milestone above is pinned.
