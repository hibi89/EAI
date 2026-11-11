# P26 — Separate owner-approved SHA-bound execution (2026-11-11 KST)

## Why

P23 advises source-specific draft goals, P15 builds a pinned manifest, and P24 recommends one of the owner's existing IDs. **A model suggestion is not permission to execute.** A missing approval bridge forced manual path traversal and made it easier to accidentally run a different goal.

## Alternatives

- A: `select-goal --execute` directly after model selection. Easy UX, but Qwen/input prompt injection or accidental matches would gain execution authority.
- B: independent `run-approved` command requiring exact manifest SHA256, selected goal SHA256 and ID copied from P24 selection; CPU rechecks the whole catalog and independent receipt. **Chosen.** Does not call any model or new network endpoint, and does not run implicit tasks.

## Usage

```powershell
python -m eai select-goal --manifest examples/sample_goal_batch.json --request "schedule" --json
# Review selected ID and both sha256 strings first.
python -m eai run-approved --manifest examples/sample_goal_batch.json --id schedule --manifest-sha256 <manifest-sha256> --goal-sha256 <selected-goal-sha256> --json
```

P14 `goal_pipeline` manifests are **not accepted** for this single-child run shortcut; use `pipeline-goals` to respect prerequisite HOLD. Each typed solver stays read-only, no data write, model generation or remote API. Independently rechecks the goal JSON receipt, selected input SHA and the entire pinned catalog after execution. User must decide whether goals and input data are appropriate; no autonomous approval or retries.

## Acceptance and limitations

Tests cover approvals, ID/SHA mismatches, manifest/child mutation, a mocked forged solver, refusal of pipeline bypass, CLI error codes and an actual P23 CSV advisor → P15 manifest → P24 selector → P26 CPU execution E2E on synthetic data. Python3.11 Linux CI required before milestone credit. Native Windows, actual Qwen/model integration and retail distribution untested. RELEASE HOLD.
