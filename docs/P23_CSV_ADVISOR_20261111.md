# P23 — Explicit CSV source advisor (2026-11-11 KST)

## Purpose and design comparison

- A: infer and execute goals directly from natural-language/Qwen output. Faster UX but changes data access scope, invites prompt injection, nonreproducible decisions and implicit model authority.
- B: source-first, bounded CPU-only schema inspection that outputs **unexecuted, editable, strict P19/P22 goal drafts**. Selected: no dependencies/API cost; zero original modification; user chooses columns and thresholds and explicitly runs existing engine.

## Usage

```powershell
python -m eai advise-csv --root examples --source sample_relationships.csv --json
```

The result prints only header names, numeric/missing/nonnumeric counts, source filename/SHA256 and two possible typed JSON drafts. It never displays raw cells, writes output files, sends prompts, executes a goal, repairs data or chooses business conclusions. To use one, review and save its `goal` JSON alongside the source CSV, then explicitly run `python -m eai solve-goal <reviewed-goal.json> --json`. JSON stdout can be redirected intentionally by the user.

## Bounds and security

- Explicit root + one relative .csv, within-root, no `..`, absolute source or symlink escape.
- File max 5MiB, rows max 20,000, headers max 32, cell max 4096 chars; encodings UTF-8-SIG/UTF-8/CP949.
- Numeric candidate heuristic: at least five fixed-point parsable rows. **This is neither semantic typing nor evidence of data quality**; bad/missing rows can cause conflict on explicit execution.
- Drafts are subject to the existing P19/P22 strict validators and independent receipt guards when later executed.
- No file output, automatic execution, LLM, web access, external provider, customer data, or permissions modification.

## Acceptance

`python -m compileall -q eai tests`; `python -m unittest discover -s tests -v`; CLI JSON/text smoke; exact GitHub CI SHA required before any progress assessment. Local Linux is not Windows/real-user proof. Provisional 50% remains until the actual test result is checked, and retail RELEASE HOLD.
