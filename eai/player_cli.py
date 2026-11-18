"""Offline-only C20/C21 Player CLI for explicitly supplied local JSON.

Never reads customer sources, runs arbitrary AXNODE skills, grants approvals,
writes original data, sends network requests, or converts previews to VERIFIED.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .contracts import MAX_DOCUMENT_BYTES, ProblemSpec, PlanSpec, strict_json
from .policy_gate import evaluate_plan_policy
from .player_runtime import execute_pure_synthetic_preview
from .local_files import read_bytes


def _read_local_contract(path: str | Path) -> dict:
    source = Path(path).expanduser()
    if (source.is_symlink() or not source.is_file()
            or source.stat().st_size > MAX_DOCUMENT_BYTES):
        raise ValueError("explicit ordinary bounded local JSON file required")
    return strict_json(read_bytes(source, MAX_DOCUMENT_BYTES))


def player_preview(
    problem_file: str | Path, plan_file: str | Path,
    *, cancel_before_step: str | None = None,
) -> dict:
    problem = ProblemSpec.validate(_read_local_contract(problem_file))
    plan = PlanSpec.validate(_read_local_contract(plan_file))
    policy = evaluate_plan_policy(problem, plan)
    if policy.disposition != "PURE_SYNTHETIC_PREVIEW_ONLY":
        return {
            "schema": "eai.player.preview.v1",
            "status": policy.disposition,
            "reason_codes": list(policy.reason_codes),
            "problem_sha256": problem.digest(),
            "plan_sha256": policy.plan_sha256,
            "execution": "DENIED",
            "real_world_verified": False,
            "automatic_learning": False,
            "active_promotion": False,
        }
    result = execute_pure_synthetic_preview(
        problem, plan, policy, cancel_before_step=cancel_before_step)
    return {
        "schema": "eai.player.preview.v1",
        "status": result.status,
        "reason_codes": [],
        "problem_sha256": result.problem_sha256,
        "plan_sha256": result.plan_sha256,
        "trace_sha256": result.trace_sha256,
        "interpreted_step_count": len(result.step_receipts),
        "step_receipts": [asdict(item) for item in result.step_receipts],
        "execution": "PURE_SYNTHETIC_NOOP_ONLY",
        "external_actions": result.external_actions,
        "original_writes": result.original_writes,
        "real_world_verified": False,
        "automatic_learning": False,
        "active_promotion": False,
    }
