"""C21 local EAI Player: deterministic PURE synthetic no-op interpreter.

This is real bounded interpretation of a harmless typed DAG, not simulated
permission to execute files, network calls, CSV reads or deploy anything.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .contracts import PlanSpec, ProblemSpec, canonical_bytes
from .policy_gate import PlanPolicyDecision, assert_pure_preview


@dataclass(frozen=True)
class PureStepReceipt:
    step_id: str
    step_sha256: str
    dependency_sha256: tuple[str, ...]
    status: str = "PURE_NOOP_INTERPRETED_NOT_VERIFIED"


@dataclass(frozen=True)
class PurePlayerPreview:
    problem_sha256: str
    plan_sha256: str
    status: str
    step_receipts: tuple[PureStepReceipt, ...]
    trace_sha256: str
    external_actions: int = 0
    original_writes: int = 0
    real_world_verified: bool = False
    promotion_authorized: bool = False


def execute_pure_synthetic_preview(
    problem: ProblemSpec, plan: PlanSpec, policy: PlanPolicyDecision,
    *, cancel_before_step: str | None = None,
) -> PurePlayerPreview:
    assert_pure_preview(problem, plan, policy)
    if cancel_before_step is not None and (
            type(cancel_before_step) is not str
            or cancel_before_step not in {s[0] for s in plan.steps}):
        raise ValueError("cancellation step must be in plan")
    visited = {}
    receipts = []
    disposition = "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED"
    for sid, op, requires, capability in plan.steps:
        if sid == cancel_before_step:
            disposition = "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED"
            break
        if op != "synthetic.noop.v1" or capability != "pure":
            raise PermissionError("no-op only interpreter")
        if any(parent not in visited for parent in requires):
            raise ValueError("invalid dependency ordering")
        deps = tuple(visited[parent] for parent in requires)
        receipt_sha = hashlib.sha256(canonical_bytes({
            "schema": "eai.player.noop.step.v1",
            "plan_sha256": policy.plan_sha256,
            "step_id": sid,
            "operator": op,
            "dependency_sha256": list(deps),
        })).hexdigest()
        visited[sid] = receipt_sha
        receipts.append(PureStepReceipt(sid, receipt_sha, deps))
    trace_sha = hashlib.sha256(canonical_bytes({
        "schema": "eai.player.noop.trace.v1",
        "problem_sha256": problem.digest(),
        "plan_sha256": policy.plan_sha256,
        "status": disposition,
        "receipts": [[r.step_id, r.step_sha256] for r in receipts],
    })).hexdigest()
    return PurePlayerPreview(problem.digest(), policy.plan_sha256,
                             disposition, tuple(receipts), trace_sha)
