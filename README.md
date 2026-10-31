> **P4 CPU 교차검증 (2026-10-31):** 두 로컬 CSV의 공통 고유 키와 숫자 열을 비교하는 `reconcile-csv` 명령이 추가됐습니다. 합계가 같아도 행별 수치가 다른 경우를 탐지하며, 결과는 `AGREE/CONFLICT/UNAVAILABLE`로 표시합니다. **실세계 사실이나 자료 독립성의 증거는 아닙니다.** [사용법·제약](docs/P4_KEYED_CSV_RECONCILIATION.md). GitHub CI는 여전히 실패하며, 실제 Windows/모델은 미검증입니다.

```powershell
python -m eai reconcile-csv examples/sample_sales.csv examples/sample_sales_source_b.csv --key year --value sales --json
```
위 명령은 의도적으로 `CONFLICT`(종료 코드 2)를 출력합니다. 두 파일의 sales 합계는 352로 같지만 2024·2025년 값이 다릅니다. CPU·SQLite·Qwen 설치 없이 실행 가능합니다.

# EAI — Elice Artificial Intelligence

Private, **local-first and CPU-first** independent EAI engine. Qwen is optional and restricted to user-input intent classification. The EAI-owned code selects and executes bounded calculations, searches, evidence verification and deterministic answer rendering. GPT-class general intelligence remains a research goal, not a current capability.

## Start (Python >=3.11, no required runtime packages)

```powershell
python -m eai health
python -m eai ask "계산 0.1+0.2"
python -m eai ask "비교 A=100,B=120"
python -m eai ask "기억해: EAI는 로컬 CPU 중심"
python -m eai ask "기억검색 EAI"
python -m eai analyze-csv examples/sample_sales.csv
python -m eai verify-csv examples/sample_sales.csv --column sales --metric sum --expected 352
python -m eai verify-csv examples/sample_sales.csv --claims examples/sample_sales_claims.json --json
python -m eai chat
```

### P3 evidence verification

`verify-csv` compares **only the user-provided CSV** to one or multiple numerical claims, and outputs per-claim VERIFIED, CONFLICT or UNAVAILABLE; it includes observed numbers, absolute tolerance and CSV SHA256. It does not authenticate real-world truth. The JSON claim file must contain 1–24 objects with string decimal fields; supported metrics are sum/min/max/avg/missing/numeric_count/text_count, with avg rounded to six decimals. The CSV is read-only (<=5MiB, <=20,000 rows, <=32 columns). Exit codes: 0 verified, 1 error, 2 conflict, 3 unavailable. No Qwen, GPU, internet, LA, or paid API is needed.

Optional `--use-qwen-intent --profile CPU_ECO` requires a separately installed local Ollama/Qwen; it only extracts IntentSpec. Optional online search requires explicit `--online` plus a local SearXNG endpoint (search queries can reach external search providers). Neither is installed or automatically enabled.

### Verification / documentation

Local Linux Python 3.13: `python -m unittest discover -s tests -v` **74 PASS** and compileall PASS. Four P3 source file SHA matches on GitHub. Full exact-repository checkout, real Windows 10/Python 3.11, real Qwen and SearXNG **unverified**. GitHub Actions currently **FAILURE** before job steps; do not infer code test failure or CI success. No Vercel/Production URL; no other repositories changed.

[STATUS](STATUS.md) · [HANDOFF](HANDOFF.md) · [P3 source validation](docs/P3_CSV_CLAIM_VERIFICATION.md) · [ADR-0002](docs/ADR-0002_EAI_COGNITIVE_OWNERSHIP.md) · [ADR-0003](docs/ADR-0003_ADAPTIVE_CPU_GPU_RESEARCH.md)
