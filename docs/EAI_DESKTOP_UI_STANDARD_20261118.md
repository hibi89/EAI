# EAI V3.1 — Native EXE Desktop Interface (P1 source-candidate spec)

**Owner choice (2026-11-18 KST):** Reuse the dark workstation arrangement from the earlier AX Dev Factory V1 reference as EAI's desktop visual direction. Reference: [`hibi89/Freelancer/docs/design/AXDEV_DESKTOP_REFERENCE_20261117.webp`](https://github.com/hibi89/Freelancer/blob/feature/axdev-owner-product-ui-20261117/docs/design/AXDEV_DESKTOP_REFERENCE_20261117.webp). The AX Dev reference is not itself an EAI implementation.

## User flow (actual Python entrypoints)

1. Double-click `RUN_EAI_DESKTOP.cmd` (uses `dist/EAI.exe` if an unsigned candidate is present, otherwise Python 3.11). Bundled entrypoint: `scripts/eai_desktop_entry.py`, `eai.desktop_app.main` (Tkinter only; no browser/server). A separate `BUILD_EAI_EXE.cmd` or manually dispatched Actions Windows build produces `EAI.exe`, **not** a certified signed release.
2. Bottom natural-language command box stays visible. **CPU 답변** sends explicit supported rule-mode commands through `DesktopBridge.ask → RuleIntentParser → EAIRunner → CognitiveEngine`, with no Qwen or online search. Existing rule grammar is intentionally narrow (`계산`, `비교`, `도움말`, explicit local notes); arbitrary instruction is `HOLD_UNSUPPORTED_REQUEST`, not an invented general AI. Adding a note requires a second local UI confirmation.
3. **설계 초안** makes a provisional `ProblemSpec` from the goal. This does **not** infer constraints, oracle or permissions. **초안 JSON 편집** allows the owner to explicitly adjust typed fields before **설계 초안 저장** creates a brand-new user-private local JSON file (exclusive create, no overwrite). Then select that local file and an **existing** AXNODE folder and click **Architect 설계 미리보기** → existing `preview_architecture` → digest-only `render_architect_explanation`. Unverified alternatives/unknowns are shown as such.
4. **AXNODE** selects an existing local library, shows a read-only SQLite node/version/parent listing, basic bounded relationship Canvas graph; never initializes a new catalog from the GUI, runs nodes or auto-promotes them. Node bodies and private source content do not go to network.
5. **Verifier** requires explicit local Journey report JSON and runs existing `audit_offline_journey_report`: receipt integrity only, **not** independent semantic/real-world verification.
6. **Player** requires explicit local ProblemSpec + PlanSpec and **a separate confirmation** before invoking existing `player_preview` → digest-only `render_player_explanation`. Only `synthetic.noop.v1` can be interpreted. No real tool, OS write, compensation, ACTIVE promotion or deployment.
7. **기록** displays bounded status-only events from the current GUI session. The separate desktop SQLite history (only upon explicit CPU command) lives in `%LOCALAPPDATA%\EAI\Desktop` on Windows, never in existing EAI_DB or AXNODE. It does not create a server.

## Design contract

- Native dark midnight navy background, violet primary command controls, teal local state, amber unverified and red HOLD. Windows title bar, left 6-tab navigation, 4 truthful static *policy* cards, central result panel and right explicit file selectors. The lower anchored command composer is the primary operator surface.
- Render only actual returned backend data. Do **not** show fake CPU/RAM data or call build screenshots runtime evidence. No Hydrogen ON toggle, credential editor, live Google API call, arbitrary `subprocess` or shell, destructive file action or unapproved external service.
- EAI Architect/Player/AXNODE remain separate modules. My Local AI / AX Dev are not runtime dependencies. High-level capability claims should match implementation; unsupported natural language abstains.

## P1/P2 boundary

**P1 source work:** `eai/desktop_bridge.py`, `eai/desktop_app.py`, `scripts/eai_desktop_entry.py`, Windows launcher/build scripts, read-only local probe tests and manual Windows build workflow. **P2 pending:** real Windows 11 native UI keyboard/DPI/color/resize tests, Tkinter event flow, PyInstaller actual EXE build/run, frozen dependency import, installation/source policy, rollback and actual AXNODE/Architect/Player integration, full CI/security/DB checks, Astra design/UX audit and independent Sol Max audit. No source candidate is a release.

**Preserve gates:** P26 exact-plan owner approval, external transfer and all Hydrogen calls HOLD, no original DB mutation, no automatic ACTIVE/real Player execution, no paid fallback, no main merge or Production. The 42 existing SWUs represent earlier backend source candidates, not evidence that this newly requested frontend was already complete. Track FE separately until official acceptance denominator is approved. Formal implementation and verification rates remain `UNASSESSED` unless all newly approved FE requirements and evidence are accounted for.
