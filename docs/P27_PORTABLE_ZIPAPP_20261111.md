# P27 — Deterministic local Python zipapp (.pyz) packaging (2026-11-11 KST)

## Design decision

- A. Self-contained Windows EXE with bundled Python/Ollama/model: large, security and licensing complexity, antivirus/SmartScreen uncertainty, and cannot be validated in current Linux environment.
- B. Small deterministic Python 3.11+ `.pyz` using stdlib ZipFile, containing only EAI Python modules. Chosen for immediate portable use with existing Python and zero dependency/API costs; **does not claim one-click Windows EXE**.

## User-initiated packaging

```powershell
python scripts/build_portable.py --output dist/eai-portable.pyz
python dist/eai-portable.pyz --version
python dist/eai-portable.pyz solve-goal examples/sample_task_schedule_goal.json --json
```

The output parent must already exist and the destination must not exist. Build only by explicit CLI request; no existing `.pyz`, data, backups, customers' files or credentials are overwritten. On build failure, only a newly created partial output is removed. Zip entries have fixed timestamp, normalized permissions and stable path order; SHA256 and ZIP integrity are verified before the success response.

Only Python `eai/**/*.py` modules plus a minimal bootloader are embedded. No examples, tests, .env, prompt history, SQLite data, model weights, user data or binaries. Internet access and a Python dependency installation are not needed for the build. Running the app requires the owner to have Python 3.11+; packaged app uses the existing CPU/local API policies.

## Acceptance and limitations

Synthetic Linux Python3.11 CI must demonstrate binary-identical repeat builds, CLI `--version`/`health`, a full `solve-goal` verified receipt from inside the `.pyz`, no overwrite, symlink refusal and archive source restriction. Native Windows, real Qwen/Ollama, antivirus/SmartScreen, installation and commercial release remain **UNVERIFIED/HOLD**. This is a packaged Python application, not a Windows EXE.
