# EAI V3.1 — SWU executable runbook (2026-11-17 KST)
Current P1 queue: EAI_P1_SWU_QUEUE.json; P2 LOCKED queue: EAI_P2_VERIFICATION_QUEUE.json; historic parent queue: EAI_INSTANT_TASK_QUEUE.md.
Canonical High-size standard: https://github.com/hibi89/hackathon-command-center-2026/blob/kmong-productization/docs/strategy/GPT6_HIGH_STANDARD_WORK_UNIT_20261117.md
Baseline exact SHA: 5ff09af317f2fe1862f829bd94b7c10202edb14d; final blueprint blob: 1b0712679d4171cd3681588e104ea5e8c6f6690d.
One P1 SWU = High one-call target of actual source caller to callee to observable result and principal fail-closed case. No CI/test harness, broad syntax/type, security audit, browser/E2E/Windows as P1 SWU. Preserve mandatory CI and immediate auth/data/secret safety checks.
Historic EAI 15 groups are decomposed into 42 units without changing requirements. C01..C36 complete, C03 missing in historic table restored. Tests and source prior evidence never treated as completed product.
Already coded candidates: 3 (all unverified); remaining 39. Initial independent first READY: EAI-SWU-011, EAI-SWU-014, EAI-SWU-016, EAI-SWU-025, EAI-SWU-038.
Each mobile ㄱ: inspect actual HEAD+AGENTS/HANDOFF/STATUS+P1 JSON, choose 4-6 disjoint READY, write real functional code and exact SHA within allowed_paths, no duplicate hardening. One pass target, two attempts max, High+owner special third only if explicitly approved; two same-cause no-progress failures HOLD and continue other READY.
Code dependencies are independent of operating-authorization dependencies; actual ACTIVE/real Player/Hydrogen, original DB, extra rights and customer writes remain HOLD. D=2 requires High review. Never loosen P26, ADR-0002, release HOLD or existing mandatory CI.
P1 completion candidate requires real caller path, normal/denied failure and local immediate safety checks, SHA. Whole test harness and acceptance run in P2 separate gate. Queue-only change adds zero implementation and no official percent.
