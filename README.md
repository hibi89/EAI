# EAI — Elice Artificial Intelligence

**Independent CPU-first EAI P1 (local, runnable, not general GPT).** Qwen is optional, strictly input classification only. EAI itself owns computing, task selection, validation, persistent memories and response rendering. Zero required paid APIs. Work stays on `feature/local-first-mvp` until real hardware and CI verification.

## Quick start — Windows 10 / Python 3.11+

From the project root run:

```powershell
python -m eai health
python -m eai ask "계산 0.1+0.2"
python -m eai ask "기억해: EAI는 로컬 독립 엔진"
python -m eai ask "기억검색 EAI"
python -m eai ask "메모목록"
python -m eai chat
```

Or run `RUN_EAI.cmd` (launcher provided, **Windows execution not yet verified**). Commands above work without Ollama, GPU, keys or internet. Python default database location: `%USERPROFILE%\.eai\eai.sqlite3`. Use `--db .\scratch.sqlite3` before `ask` for an isolated local test.

### Supported tasks

- `계산 12*(3+4)`: CPU bounded exact Fraction/Decimal arithmetic.
- `기억해: 내용` / `메모추가 내용`: explicit user note stored in SQLite, maximum 2,000 characters; duplicates do not create new rows.
- `기억검색 프로젝트` / `기억 프로젝트`: local note search plus saved source snippets (sources are **UNVERIFIED**).
- `메모목록`: up to 10 recent personal notes.
- `검색 최신 AI 모델`: only if explicitly enabled, requires externally configured local SearXNG service.
- `도움말`: the supported narrow capabilities; unsupported general GPT requests return limitations rather than fabricated answers.

Before adding the `user_notes` table to an existing SQLite DB, EAI creates a consistent local backup named `<db>.pre-notes-*.bak` in the same directory. Both the database and backup contain private conversation content and are Git-ignored. New user notes are additive, kept separate from unverified web snippets. No automatic model training.

### Optional local Qwen input-only classification

Ollama must be installed separately with a compatible locally downloaded, licensed model; EAI does not download or configure it:

```powershell
python -m eai --use-qwen-intent --profile CPU_ECO ask "7 곱하기 6은?"
```

`CPU_ECO` requests `num_gpu=0` for Qwen classification. `OLLAMA_DEFAULT` uses Ollama's default offloading. Neither is an empirically selected hardware optimum. The Qwen output is a strictly validated IntentSpec, never the authored final answer.

### Optional online lookup

A user-operated local SearXNG endpoint must support JSON; queries **may leave the PC** through its external search providers:

```powershell
python -m eai --searxng-url http://127.0.0.1:8080 --online ask "검색 최신 AI 모델"
```

No `--online` = no search requests. Search cache expires and stale data must not be described as live.

### Tests / actual status

```powershell
python -m compileall -q eai tests
python -m unittest discover -s tests -v
```

Local Python 3.13.5 verification: **36 PASS / 0 FAIL**, including simulated loopback HTTP integration and legacy SQLite backup. Separate CLI process note/recall/math/SQLite reopen PASS. **Not verified:** exact remote CI success, Windows user PC, real Qwen inference, actual SearXNG service, GPU/CPU performance. GitHub Actions has 12 completed runs with failure and zero job steps; cause not yet established. Do not infer a code defect or CI PASS.

### Design

[ADR-0002: EAI owns intelligence](docs/ADR-0002_EAI_COGNITIVE_OWNERSHIP.md) · [ADR-0003: CPU/GPU R&D](docs/ADR-0003_ADAPTIVE_CPU_GPU_RESEARCH.md) · [STATUS](STATUS.md) · [HANDOFF](HANDOFF.md)

No LA/HAE changes, frontend, public service, deployment or Vercel project. EAI's GPT-class ambition remains long-term research, not current functionality.
