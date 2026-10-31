# EAI — STATUS (2026-10-31 KST)

## Truthful product state
Private repository `hibi89/EAI`, branch `feature/local-first-mvp` (no main merge). EAI independently solves a bounded set of tasks; **Qwen is INPUT classification only** when enabled and cannot write user notes or generate final EAI answers. Python >=3.11 stdlib, SQLite, optional Ollama/SearXNG. Backend first, frontend last. Original HAE/LA, SOVIA and other repos untouched.

## P1 implemented
- P0: CPU exact calculation, Qwen IntentSpec v1 input parser and CPU rule fallback, deterministic ResultSpec response, explicit online search and SQLite cache/history.
- P1: original-text-gated `기억해`/`메모추가`, `메모목록`, `기억검색`; local notes separate from web snippets, idempotent duplicate note insertion, bounded input and parameterized SQL with literal wildcard escaping.
- Automatic SQLite consistent snapshot `<db>.pre-notes-*.bak` before adding notes table to an **existing** local database; Git ignore prevents database and snapshot uploads.
- Real loopback HTTP integration tests with fake local Ollama and SearXNG, including a redirect denial case. Does NOT establish real public search or actual Qwen availability.

## Actual verification
- Container Linux Python 3.13.5: compileall PASS; `python -m unittest discover -s tests -v` **36 PASS / 0 FAIL / 0 SKIP**.
- Separate CLI processes: note created/retrieved/listed from SQLite, one note and 8 conversation turns persisted; `계산 0.1+0.2 = 0.3` PASS.
- Remote code verified by file fetch and selected Git blob SHA comparisons; remote `storage.py` is semantically reviewed but formatted differently from local test copy, so a complete byte-identical remote-checkout pass is UNVERIFIED.

## GitHub Actions — failure, cause unknown
- Latest inspected run `41200369167` (commit `bb1814e5a302563f886cd5c20b2c5526b26ae8e5`): completed FAILURE, no job steps, runner_name empty. Job log download gave BlobNotFound. Prior 11 runs had the same ~3-second failure outcome.
- This is **not a confirmed code test failure** nor CI success. Stop pointless reruns; inspect repository Actions runner/permission/billing setup using authorized UI or effective logs when accessible.

## Not completed / next
- Owner Windows 10 Python 3.11, `RUN_EAI.cmd`, real Qwen/Ollama inference, and real SearXNG: NOT VERIFIED.
- LA adapter, broader independent solvers, RAG, learning, hierarchical reasoning, autonomous GPT-class generation, CPU/GPU optimum, GUI, deployment: NOT IMPLEMENTED.
- Prioritize owner usage feedback on CLI/memory and one useful independent solver next; verify real Windows only when feasible, no forced model download or paid API. Maintain test, privacy, schema versioning and note backups.

No Production URL, Vercel deployment or public endpoint: N/A.
