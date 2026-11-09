## P19 exact-source gate — 2026-11-10 KST

- Feature+test SHA **`d376a4dda5595385bd6a2f189b5e20e6090e4b27`** [GitHub Actions 42691179558](https://github.com/hibi89/EAI/actions/runs/42691179558) **completed/success**, Python3.11 Ubuntu: `python -m compileall -q eai tests` PASS, `python -m unittest discover -s tests -v` **417/417 PASS, 0 FAIL/0 SKIP**, CLI `python -m eai --version` and `health` PASS. Includes 22 new P19 tests with actual temporary CSV, strong +/-/zero associations, high precision, incomplete data, no-causation warning, raw-value non-disclosure, SHA/tamper, forged receipts, source size/row limits, CP949/BOM, CLI status codes, P12 batch and P14 dependent HOLD. Doctor 10 legacy checks covered in full unit suite; no dedicated P19 doctor sample added.
- First source SHA `c01d9f432aa261cd7dd00ad3d288de79dc3fa06c` [Actions 42690998979](https://github.com/hibi89/EAI/actions/runs/42690998979) **417 executed / 2 FAIL** caused by incorrect test expectation for nonlinear synthetic x-y correlation (0.980609, not 1.0), and checking zero-variance y-z instead of x-z. Feature solver + verifier unchanged; updated expectations passed full rerun at SHA above.
- Independent CPU result is descriptive **Pearson correlation only**, no significance/causality/forecasting, and no real user workload or native Windows evidence. Estimated total product 45%; retail release HOLD, Windows/Qwen/Ollama/SearXNG/customer/production unverified.

---

## P18 exact-source acceptance — 2026-11-10 KST

- GitHub `feature/local-first-mvp` feature+tests SHA **`ef220a017c3f7a14d20aaadfdbcdb40bd3feec28`**, [Actions #42688535530](https://github.com/hibi89/EAI/actions/runs/42688535530) **completed/success** at Linux Python 3.11: compileall PASS, **395/395 unittest PASS/0 FAIL/0 SKIP**, CLI smoke PASS. Previous P17 baseline 375/375 PASS. P18 adds 20 targeted synthetic SQLite tests (DB unchanged, source/hash tamper rejection, duplicate/null and empty, read-only/authorizer-bound schema, path escape, 20K row guard, CLI 0/1/2/3, batch & DAG block).
- P18 validation: read-only actual on-disk synthetic SQLite created in temporary CI workspace. Independent receipt recheck PASS; no actual customer DB or original values uploaded. `doctor` remains a 10-check bundle for six committed text example goals; P18 is tested by dedicated P18 tests instead of doctor.
- Product-wide **44% provisional** (+1%p from 43) for genuinely new SQLite data skill. Not evidence of general intelligence or retail readiness. **Windows owner native, real Qwen/Ollama, live SearXNG, paid/customer usage, installed package and Production UNVERIFIED; RELEASE HOLD.**

---

## P16/P17 validated acceptance — 2026-11-10 KST

- **Test source gate PASS:** `9b0b7438cd0e8756e87c7ca4d03d23a731773d91` [GitHub Actions 42680542935](https://github.com/hibi89/EAI/actions/runs/42680542935) Linux Python3.11 compileall PASS, **375/375 unittest PASS/0 FAIL**, CLI smoke PASS. P16 generated 28 new tests, P17 generated 27 new tests; batch/pipeline gating, forged evidence, SHA source changes, size/row/column caps, CP949, status codes, synthetic doctor included.
- **CLI expected sample result:** `csv_quality` and `csv_schema_drift` checked-in fixtures show `CONFLICT`, therefore `solve-goal ... --json` returns exit **2 by design**; `doctor --json` requires their expected CONFLICT and returns exit **0** when all **10/10** checks pass.
- **Previous intermediate P17 CI:** SHA `eb522c34b4890198e3cb23196f32e1abcd56a946` two obsolete test assertions failed (375 total, 373 PASS). Follow-up SHA above contains test-only updates and proved total 375 PASS.
- **Still UNVERIFIED:** actual Windows/owner hardware, customer data, live Qwen/Ollama, SearXNG, permissions/business workflow, installation, commercial/release rights. **Product READY/HOLD: HOLD**.

---

## Latest exact-source gate — P15 2026-11-10 KST

- **Gate S PASS:** `c35269299f0cdfaa42c51eb8351db50b9e7ec93d`, [GitHub Actions #42676269100](https://github.com/hibi89/EAI/actions/runs/42676269100); Linux Python3.11 **320/320 unittest PASS, 0 FAIL**; syntax, CLI smoke PASS. P15 19 integration/regression tests include CLI output and explicit saved-manifest execution via batch/pipeline.
- **Gate Windows native / installed Qwen / local SearXNG / real customer source / retail release:** NOT VERIFIED and HOLD. A CI green status proves only the tested scope. `make-manifest` itself is stdout-only/read-only.
- Historical 301/301 CI at P13/P14 SHA `bbd01576eed2573ffeab5a70eec0662fcb40bad0` remains a valid past proof, not the current source SHA.

---

## Current acceptance gates — 2026-11-10 KST

- **Gate S (CI exact source): PASS** at `bbd01576eed2573ffeab5a70eec0662fcb40bad0`, [Actions #42675220982](https://github.com/hibi89/EAI/actions/runs/42675220982); Linux Python3.11 `compileall` + **301/301 unittest PASS, 0 FAIL, 0 SKIP**, CLI smoke PASS. Includes P13 doctor 8-sample tests and P14 pipeline positive/negative, forged receipt, path/sha checks.
- **Gate W native Windows10/11 and owner hardware: NOT TESTED.** `RUN_EAI_DOCTOR.cmd` exists but was not run on owner's system; manual observation still needed.
- **Gate L real local Ollama/Qwen model (input classification only): NOT TESTED.** Stubbed model responses are not live proof.
- **Gate R optional local SearXNG or real customer source: NOT TESTED.** No remote search or private data sent.
- **Gate P customer release, packaging, rights, paid distribution: HOLD**, not a Vercel/Production site.
- Historical source run 42675080093 was **301 tests executed / 2 failure**, outdated test assertions indexed the previous last diagnostic; corrected by the exact successful SHA above. Old P13/P14 Job 0 runs were pre-step infrastructure evidence, not latest code regression.

---

> **2026-10-31 P0 new gate:** Independent EAI engine local-source suite 21 PASS/0 FAIL/0 SKIP (Python 3.13.5). CLI `python -m eai --db /tmp/eai_p0_demo2.sqlite ask '계산 0.1+0.2'` returned `0.3` without Qwen. Stubbed structured Qwen response never synthesized final answers; out-of-schema data rejected. Search consent/cache and restart history covered in offline tests. **GitHub exact-commit CI, actual Windows 3.11, actual Qwen and SearXNG are NOT tested.** No numeric CPU/GPU 'golden ratio' measured.

# EAI acceptance gates and test matrix

## Gate S — source test (no network or model)

Command from repository root: python -m unittest discover -s tests -v
Additional: python -m compileall -q eai tests; python -m eai --version; python -m eai health.

Test targets: no paid services, synthetic conversation and restart memory, unauthorized freshness warning, mock online search + TTL reuse, failed retrieval warning, loopback URL enforcement, rejection of invalid questions/tool duplicates and bounded JSON parsing. These are **synthetic**, not proof of real Ollama or SearXNG operation. A manually reconstructed local source mirror (not byte-identical to GitHub) executed Python 3.13.5 compileall/CLI smoke and 15/15 unittests successfully on 2026-10-31 KST. Exact GitHub committed source CI conclusion remains unverified.

## Gate L — real local model (owner Windows only)

Prerequisite: Python 3.11+, Ollama installed and serving at 127.0.0.1:11434, model qwen2.5:3b downloaded. Verify CLI ask Korean answer; chat follow-up; process restart and persistence; missing model/stop server gives clear failure; CPU fallback can respond on older laptop. Measure RAM/time and retain minimal logs without personal text.

## Gate W — opt-in online retrieval

Prerequisite: local SearXNG and valid JSON search endpoint set by owner, explicit --online. Verify one live query returns correct provider source URLs, second same query consumes cache without new request, TTL expiration refreshes, offline or disabled provider returns warning, no access to remote/localhost arbitrary ports via an injected endpoint, no secret in query. A search hit must display as UNVERIFIED.

## Gate P — production/quality

Not applicable to local CLI until owner approves release/deployment. No Vercel project, domain, network-facing server or Production URL is created by this branch. Later, test backup/restore, system resource limits, workflow permissions, prompt injection and API rate limits before public exposure.

## Status rule

Code present != tests PASS. CI green != real Ollama PASS. A copied snippet != verified fact. A successful local smoke != production readiness. Record exact commit SHA, command, PASS/FAIL/SKIP and environment at every gate.
