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


@dataclass(frozen=True)
class PureTraceAudit:
    """Independent deterministic replay agreement, never semantic truth."""
    status: str
    expected_trace_sha256: str
    matching_steps: int
    grants_real_authority: bool = False


def audit_pure_player_trace(
    problem: ProblemSpec, plan: PlanSpec, policy: PlanPolicyDecision,
    claimed: PurePlayerPreview, *, cancel_before_step: str | None = None,
) -> PureTraceAudit:
    """Recompute all no-op step hashes and cancellation outcome before review."""
    if type(claimed) is not PurePlayerPreview:
        raise ValueError("explicit typed trace required")
    expected = execute_pure_synthetic_preview(
        problem, plan, policy, cancel_before_step=cancel_before_step)
    if claimed != expected:
        return PureTraceAudit("REJECTED_UNREPRODUCIBLE_PURE_TRACE",
                              expected.trace_sha256, 0)
    return PureTraceAudit("PURE_TRACE_REPLAY_MATCH_UNVERIFIED",
                          expected.trace_sha256, len(expected.step_receipts))


# EAI-SWU-028: real safe caller -> gate -> pure interpreter -> replay.
@dataclass(frozen=True)
class PurePlayerFlow:
    status: str
    problem_sha256: str
    plan_sha256: str
    trace_sha256: str | None
    interpreted_steps: int
    reason_codes: tuple[str, ...]
    replay_status: str
    original_writes: int = 0
    external_actions: int = 0
    grants_real_authority: bool = False
    independent_real_world_verification: bool = False


def run_bounded_pure_player(
    problem: ProblemSpec, plan: PlanSpec, *,
    interpret_pure_noop: bool = False,
    architect_truth: str = "UNVERIFIED",
    evidence_review_required: bool = False,
    cancel_before_step: str | None = None,
) -> PurePlayerFlow:
    """Only explicit no-op interpretation can proceed after recomputed gate."""
    from .policy_gate import evaluate_problem_review_policy
    if type(interpret_pure_noop) is not bool:
        raise ValueError("explicit boolean pure interpretation switch")
    policy = evaluate_problem_review_policy(
        problem, plan, architect_truth=architect_truth,
        evidence_review_required=evidence_review_required)
    if policy.disposition != "PURE_SYNTHETIC_PREVIEW_ONLY":
        return PurePlayerFlow(
            "HOLD_POLICY_DENIED", policy.problem_sha256,
            policy.plan_sha256, None, 0, policy.reason_codes, "NOT_RUN")
    if not interpret_pure_noop:
        return PurePlayerFlow(
            "PURE_ELIGIBLE_NOT_INTERPRETED", policy.problem_sha256,
            policy.plan_sha256, None, 0, (), "NOT_RUN")
    # Existing interpreter revalidates policy independently before each call.
    trace = execute_pure_synthetic_preview(
        problem, plan, policy, cancel_before_step=cancel_before_step)
    audit = audit_pure_player_trace(
        problem, plan, policy, trace, cancel_before_step=cancel_before_step)
    if audit.status != "PURE_TRACE_REPLAY_MATCH_UNVERIFIED":
        raise ValueError("independent pure replay rejected trace")
    if trace.external_actions or trace.original_writes or trace.promotion_authorized:
        raise PermissionError("untrusted Player attempted side-effect claim")
    return PurePlayerFlow(
        trace.status, trace.problem_sha256, trace.plan_sha256,
        trace.trace_sha256, audit.matching_steps, (),
        audit.status)
