# EAI P9 — displayed receipt evidence integrity (2026-11-10 KST)

## Purpose
The P8 guard already independently validates normalized final scores, raw ranking,
winners, selected hard-constraint pairs and the Pareto frontier. It did not bind
the *displayed* criterion configuration and per-option evidence fields, detailed
constraint numbers, dominated_by list or execution trace. A forged receipt could
therefore display false intermediate reasons while the top-line result remained
unchanged and P8 returned PASS.

## Alternatives and decision
- **A. Replay the whole solver and compare its serialized output:** simpler
  conceptual assertion, but couples the independent guard to the same solver
  implementation and repeats all work; a shared defect could pass unnoticed.
- **B. Independently recompute only the missing evidence fields from the
  validated original ChoiceGoal:** small pure-stdlib change, bounded CPU cost,
  no new OS permissions, APIs, data writes or dependencies. **Selected B.**

## Implementation contract
- New `eai/receipt_evidence.py` checks `DECISION_VERSION`, exact displayed
  criteria, each feasible option's actual/normalized/weight/out-of-bounds
  evidence, each excluded option's empty detail, independent pairwise Pareto
  `dominated_by`, actual versus required constraint values and the fixed
  versioned solver trace.
- `eai/receipt_guard.py` only calls this new fail-closed verifier *after*
  existing P8 verification; a mismatch raises ValueError and prevents PASS.
  CSV receipt logic, P0–P7 solver code, user data and CLI exit semantics are
  unchanged. The P9 new verification check identifier is `detail_evidence`.
- New `tests/test_receipt_evidence_p9.py` includes valid, tampered and
  TIE/UNAVAILABLE original solver receipts. No network/model/data write.
- This does not prove the user's original measurements or source authenticity;
  it merely validates that reported details agree with those inputs.

## Evidence and remaining acceptance gates
- **Executed isolated local Python 3.13.5 smoke:** compileall PASS,
  9/9 isolated helper checks PASS using stdlib substitute domain classes and
  confirmed source-rendering behavior. This is **not** the byte-identical full
  GitHub checkout and is not the new integration test suite passing.
- **Not executed:** GitHub-exact full suite (`python -m unittest discover -s tests -q`),
  P9 new integration tests on complete real EAI repository, Windows Python
  3.11, actual user CSV data, Ollama, SearXNG, GPU and production.
- Existing GitHub Actions current HEAD failed before visible Python test steps.
  New code does not change its workflow/billing/permissions; do not equate
  Actions FAILED with a proven EAI runtime regression, or claim green.
- To verify next on genuine checkout:
  `python -m compileall -q eai tests`;
  `python -m unittest tests.test_receipt_evidence_p9 -v` (using discovery if
  tests package path is not importable);
  `python -m unittest discover -s tests -q`;
  `python -m eai solve-goal examples/sample_hardware_decision.json --json`;
  `python -m eai solve-goal examples/sample_csv_audit_goal.json --json`.
- No release or completion-rate increase without passing integration on exact
  source and further customer-level readiness.

## 2026-11-10 verified remote-source acceptance (supersedes pre-CI caveat)
- **Code + test SHA:** `da48d1764f8a369905ef34bd6810cb738efb8a2b` on `feature/local-first-mvp`.
- **Actions:** [offline-checks #42659433939](https://github.com/hibi89/EAI/actions/runs/42659433939), completed/success. Checked job steps: actions/checkout@v4, setup-python@v5, compileall, full `python -m unittest discover -s tests -v`, `python -m eai --version`, `python -m eai health`, all success.
- **Actual test log:** `Ran 211 tests in 4.645s`, `OK` (**211 pass, 0 fail**). New P9 tests 10 are included in this exact-source complete suite.
- Original earlier Actions runner failure did not establish a product-code error; the next commit's green runner does not diagnose the historical failure root cause. No permission/billing change was made.
- **Not verified:** local owner's Windows10/11 and real Qwen/Ollama/SearXNG, any private customer material, installer and customer release gates. No source/write/network/production changes.
- This note may be committed as documentation-only `[skip ci]`; in that case a later HEAD without Actions is not a regression because the tested code and tests remain at the SHA above. Compare diffs before treating them as identical.
