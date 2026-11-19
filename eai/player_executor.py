"""EAI-SWU-029 isolated EAI Player operator port — pure in-memory only.

A port is NOT a registered OS/service tool. This module contains no callable
plugin, network transport, subprocess, general Python evaluator, or file writer.
It deliberately refuses every real operator until separate High/owner GO.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import ProblemSpec, PlanSpec
from .policy_gate import (
    evaluate_isolated_player_port,
    evaluate_problem_review_policy,
)
from .player_runtime import (
    execute_pure_synthetic_preview, audit_pure_player_trace,
)


@dataclass(frozen=True)
class PureOperatorPortReceipt:
    status: str
    problem_sha256: str
    plan_sha256: str
    requested_step: str
    trace_sha256: str | None
    observed_steps: tuple[str, ...]
    reason_codes: tuple[str, ...]
    interpreter: str = "EAI_PURE_IN_MEMORY_NOOP_ONLY"
    real_tool_calls: int = 0
    original_writes: int = 0
    network_calls: int = 0
    authorized_active_promotion: bool = False
    semantic_verification: bool = False


def dispatch_isolated_pure_player(
    problem: ProblemSpec, plan: PlanSpec, *,
    requested_step: str,
    interpret_synthetic: bool = False,
    architect_truth: str = "UNVERIFIED",
    evidence_review_required: bool = False,
    cancel_before_step: str | None = None,
) -> PureOperatorPortReceipt:
    """Scoped step must exist in a fully typed, entirely pure bounded DAG.

    This runs the existing interpreter only after explicit opt-in and a freshly
    recomputed identical plan policy; output never grants real tool authority.
    """
    if type(interpret_synthetic) is not bool:
        raise ValueError("explicit local no-op interpretation flag required")
    port = evaluate_isolated_player_port(
        problem, plan, step_id=requested_step,
        architect_truth=architect_truth,
        evidence_review_required=evidence_review_required)
    if port.status != "PURE_NOOP_IN_MEMORY_ONLY":
        return PureOperatorPortReceipt(
            "HOLD_SCOPED_PLAYER_PORT", port.problem_sha256, port.plan_sha256,
            port.step_id, None, (), port.reason_codes)
    if not interpret_synthetic:
        return PureOperatorPortReceipt(
            "HOLD_EXPLICIT_SYNTHETIC_INTERPRETATION_REQUIRED",
            port.problem_sha256, port.plan_sha256,
            port.step_id, None, (), ("EXPLICIT_LOCAL_ONLY_OPT_IN_MISSING",))
    if (cancel_before_step is not None and
            cancel_before_step not in {s[0] for s in plan.steps}):
        raise ValueError("unbound cancellation step")
    policy = evaluate_problem_review_policy(
        problem, plan, architect_truth=architect_truth,
        evidence_review_required=evidence_review_required)
    if (policy.disposition != "PURE_SYNTHETIC_PREVIEW_ONLY"
            or policy.plan_sha256 != port.plan_sha256):
        raise PermissionError("scoped plan policy changed before synthetic run")
    trace = execute_pure_synthetic_preview(
        problem, plan, policy, cancel_before_step=cancel_before_step,
        requested_step=requested_step)
    audit = audit_pure_player_trace(
        problem, plan, policy, trace, cancel_before_step=cancel_before_step,
        requested_step=requested_step)
    if (audit.status != "PURE_TRACE_REPLAY_MATCH_UNVERIFIED"
            or audit.expected_trace_sha256 != trace.trace_sha256
            or trace.real_world_verified or trace.promotion_authorized
            or trace.original_writes or trace.external_actions):
        raise PermissionError("pure trace integrity or side-effect promise rejected")
    steps = tuple(item.step_id for item in trace.step_receipts)
    if len(steps) != audit.matching_steps:
        raise ValueError("incoherent step receipt count")
    return PureOperatorPortReceipt(
        trace.status, port.problem_sha256, port.plan_sha256,
        port.step_id, trace.trace_sha256, steps, ())
