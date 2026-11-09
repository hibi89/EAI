# P20 — CPU-only local text evidence search (2026-11-10 KST)

Ninth bounded typed goal `local_evidence_search`. This does not answer natural-language questions, interpret source credibility, or invent narrative conclusions. It locates exact evidence line numbers in explicitly named owner-controlled local files.

## Architecture options

- **A: vector embedding/LLM retrieval**: flexible semantic retrieval but model compute, memory and leakage/interpretation risks; external API rights and offline portability complicate use.
- **B: exact-token verified CPU line search**, files bounded with explicit allowlist and deterministic ranking. **Chosen** for CPU-first independent evidence ownership, zero recurring cost, reproducible receipts and local-only data.

## Contract

```json
{
  "version": 1,
  "kind": "local_evidence_search",
  "goal": "Find evidence for a documented risk",
  "sources": ["notes.md", "policy.txt"],
  "terms": ["risk", "mitigation"],
  "max_results": 5,
  "include_snippets": false
}
```

Save `goal.json` alongside explicitly selected files and call `python -m eai solve-goal goal.json --json`. Or try `python -m eai solve-goal examples/sample_local_evidence_goal.json --json` (synthetic fixtures, exit 0 / AGREE expected). Case-insensitive exact Unicode word tokens, requiring **all specified terms on the same line**. It is not a cross-line or synonym match. Score: term occurrence count (capped at 1000) plus +5 adjacent phrase bonus in user term order; sort by score descending then owner-selected file order and 1-based line position. Returns filename+SHA256+line count per source, total matching lines, up to `max_results` ranked hits. `UNAVAILABLE` exit 3 means no exact matching line, not that the proposition is disproven.

## Permission/privacy boundary

- 1–8 specifically named UTF-8(.BOM) `.txt`/`.md` files in the goal directory (no automatic traversal; relative path and symlink escape prevention; ambiguous duplicate basename rejected). Each file <=256 KiB, <=5,000 lines, <=2,000 characters per line. 1–5 distinct exact query terms <=32 characters. Result max 1–20.
- Default `include_snippets=false` produces only filename/line/ranking and hashes. Only an **explicit** user-edited `include_snippets=true` outputs the first <=160 characters from a matched source line to the **local CLI**, which could expose secrets in a terminal log. Never paste private snippets in public tickets.
- No writes, external models or APIs, network access, shell/SQL evaluation or implicit collection of directory contents. Strict single-goal JSON and all manifest SHA256 gates are checked. Source sha256 checked pre/post primary scan and independently before/after a separate Counter-based verifier re-indexing the original bytes; altered receipts are rejected.
- P12 SHA-pinned batch and P14 dependency-gated pipeline work automatically. `AGREE` means exact lines found, not source truth; `UNAVAILABLE` blocks dependent tasks until manual review.
- Python 3.11 standard library. Existing six fixtures in offline doctor and their 10 checks are preserved; P20 uses dedicated synthetic text-source integration tests.

## Acceptance

After writing source: exact SHA Actions `compileall`, whole unittest regression, CLI smoke, no model required; separate synthetic sample CLI result may be exercised manually. No real customer files or user Windows/Qwen/Ollama/SearXNG tested yet. Product remains RELEASE HOLD until explicit owner release approval.

## Exact-source verification record

- Initial SHA `60493c71ae3d091a8359b908b81aad238f150f33` [Actions 42693891473](https://github.com/hibi89/EAI/actions/runs/42693891473): 437 tests attempted / 2 ERROR (unsupported extension resolved before path/extension rejection).
- Corrected exact P20 SHA `f73e97e5951549c72872b4d3213c159abecaa095` [Actions 42694085666](https://github.com/hibi89/EAI/actions/runs/42694085666): Linux Python3.11 **437/437 PASS / 0 FAIL**, syntax + CLI smoke PASS. P20 adds 20 tests. Later P21/P22 regression at `88af3412d59dad8ea848322bdb75292adb7db9e4` **475/475 PASS**. Do not infer Windows/real owner documents tested.
