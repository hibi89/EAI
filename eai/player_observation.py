"""EAI-SWU-030 idempotent in-memory observation and no-op compensation.

This is NOT a real rollback implementation. No original state is changed, so
compensation may only note removal of an in-memory synthetic intent. Any real
tool/state claim must HOLD until separately approved and verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .contracts import ProblemSpec, PlanSpec, canonical_bytes
from .player_executor import (
    PureOperatorPortReceipt, dispatch_isolated_pure_player,
)


@dataclass(frozen=True)
class PurePlayerCompensation:
    status: str
    problem_sha256: str
    plan_sha256: str
    request_step: str
    source_trace_sha256: str | None
    compensation_sha256: str | None
    reason_codes: tuple[str, ...]
    idempotent: bool = True
    compensating_action_executed: bool = False
    original_files_modified: bool = False
    rollback_of_real_action_proven: bool = False
    real_world_verified: bool = False


def observe_and_compensate_pure_port(
    problem: ProblemSpec, plan: PlanSpec,
    receipt: PureOperatorPortReceipt, *,
    request_compensation: bool = False,
    architect_truth: str = "UNVERIFIED",
    evidence_review_required: bool = False,
    cancel_before_step: str | None = None,
) -> PurePlayerCompensation:
    """Reproduce the deterministic synthetic trace, then derive one stable SHA.

    Repeated identical requests produce the same compensation receipt. There
    is no file write, external rollback call, process, or mutable action.
    """
    if (type(receipt) is not PureOperatorPortReceipt
            or type(request_compensation) is not bool):
        raise ValueError("typed pure Player receipt and boolean switch required")
    if (receipt.real_tool_calls or receipt.original_writes or
            receipt.network_calls or receipt.authorized_active_promotion or
            receipt.semantic_verification):
        raise PermissionError("privileged side-effect claim rejected")
    if not request_compensation:
        return PurePlayerCompensation(
            "HOLD_EXPLICIT_COMPENSATION_REQUEST_REQUIRED",
            receipt.problem_sha256, receipt.plan_sha256,
            receipt.requested_step, receipt.trace_sha256, None,
            ("COMPENSATION_NOT_REQUESTED",))
    try:
        expected = dispatch_isolated_pure_player(
            problem, plan, requested_step=receipt.requested_step,
            interpret_synthetic=True, architect_truth=architect_truth,
            evidence_review_required=evidence_review_required,
            cancel_before_step=cancel_before_step)
    except (ValueError, KeyError, PermissionError):
        return PurePlayerCompensation(
            "HOLD_UNREPRODUCIBLE_PURE_TRACE",
            receipt.problem_sha256, receipt.plan_sha256,
            receipt.requested_step, receipt.trace_sha256, None,
            ("INDEPENDENT_LOCAL_REPLAY_REJECTED",))
    if expected != receipt or receipt.trace_sha256 is None or (
            receipt.status not in {
                "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED",
                "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED"}):
        return PurePlayerCompensation(
            "HOLD_UNREPRODUCIBLE_PURE_TRACE",
            receipt.problem_sha256, receipt.plan_sha256,
            receipt.requested_step, receipt.trace_sha256, None,
            ("REPLAY_HASH_OR_POLICY_MISMATCH",))
    fingerprint = sha256(canonical_bytes({
        "schema": "eai.player.pure.compensation.v1",
        "problem_sha256": receipt.problem_sha256,
        "plan_sha256": receipt.plan_sha256,
        "requested_step": receipt.requested_step,
        "trace_sha256": receipt.trace_sha256,
        "status": receipt.status,
        "reason": "NO_REAL_SIDE_EFFECTS_TO_REVERSE",
    })).hexdigest()
    return PurePlayerCompensation(
        "PURE_IN_MEMORY_INTENT_COMPENSATED_NOT_REAL_ROLLBACK",
        receipt.problem_sha256, receipt.plan_sha256,
        receipt.requested_step, receipt.trace_sha256, fingerprint,
        ("NO_REAL_SIDE_EFFECTS_TO_REVERSE",))
