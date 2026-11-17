"""C20 strict local, non-authorizing plan policy preview.

Pure synthetic no-op is the only permitted executable operator. This gate
never mints owner approval, reads original files, grants local.read, or executes.
EAI PlanSpec is treated as untrusted until reconstructed and revalidated.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .contracts import PlanSpec, ProblemSpec, canonical_sha256

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class PlanPolicyDecision:
    plan_sha256: str
    problem_sha256: str
    disposition: str
    reason_codes: tuple[str, ...]
    permitted_sandbox_steps: tuple[str, ...]
    original_write_allowed: bool = False
    external_send_allowed: bool = False
    grants_real_authority: bool = False


def _validated_problem(problem: ProblemSpec) -> ProblemSpec:
    """Reject dataclass.replace or manually constructed policy-bound problems."""
    if type(problem) is not ProblemSpec:
        raise ValueError("typed EAI problem required")
    try:
        rebuilt = ProblemSpec.validate({
            "version": problem.version, "id": problem.id,
            "goal": problem.goal, "domain": problem.domain,
            "state_refs": list(problem.state_refs),
            "assumptions": list(problem.assumptions),
            "hard_constraints": list(problem.hard_constraints),
            "objectives": list(problem.objectives), "oracle": problem.oracle,
            "permissions": list(problem.permissions),
            "budget": {"max_steps": problem.budget[0],
                       "max_seconds": problem.budget[1]},
            "risk": problem.risk,
        })
    except (TypeError, IndexError, KeyError, AttributeError) as exc:
        raise ValueError("invalid typed problem fields") from exc
    if rebuilt != problem:
        raise ValueError("untrusted problem representation")
    return rebuilt


def _validated_plan(plan: PlanSpec) -> PlanSpec:
    if type(plan) is not PlanSpec:
        raise ValueError("typed EAI plan required")
    raw = {
        "version": plan.version,
        "problem_sha256": plan.problem_sha256,
        "steps": [
            {"id": sid, "operator": op, "requires": list(requires),
             "capability": capability}
            for sid, op, requires, capability in plan.steps
        ],
        "budget": {"max_steps": plan.budget[0], "max_seconds": plan.budget[1]},
    }
    rebuilt = PlanSpec.validate(raw)
    if rebuilt != plan:
        raise ValueError("untrusted plan representation")
    return rebuilt


def plan_digest(plan: PlanSpec) -> str:
    plan = _validated_plan(plan)
    return canonical_sha256({
        "schema": "eai.player.plan.v1",
        "problem_sha256": plan.problem_sha256,
        "steps": [[sid, op, list(requires), cap]
                  for sid, op, requires, cap in plan.steps],
        "budget": list(plan.budget),
    })


def evaluate_plan_policy(
    problem: ProblemSpec, plan: PlanSpec, *,
    proposed_approval_hash: str | None = None,
) -> PlanPolicyDecision:
    problem = _validated_problem(problem)
    plan = _validated_plan(plan)
    digest = plan_digest(plan)
    reasons = []
    if plan.problem_sha256 != problem.digest():
        reasons.append("CROSS_PROBLEM_PLAN")
    if problem.risk != "LOW":
        reasons.append("NON_LOW_RISK")
    if plan.budget[0] > problem.budget[0] or plan.budget[1] > problem.budget[1]:
        reasons.append("PLAN_EXCEEDS_PROBLEM_BUDGET")
    if not set(step[3] for step in plan.steps) <= set(problem.permissions):
        reasons.append("CAPABILITY_NOT_IN_PROBLEM")
    if any(op != "synthetic.noop.v1" or cap != "pure"
           for _sid, op, _req, cap in plan.steps):
        reasons.append("REAL_OR_UNSUPPORTED_OPERATOR_BLOCKED")
    # Caller-controlled approval text never becomes authority, even if a
    # syntactically correct SHA is supplied. It must not affect local no-op.
    if proposed_approval_hash is not None:
        if (type(proposed_approval_hash) is not str
                or not _DIGEST.fullmatch(proposed_approval_hash)):
            raise ValueError("invalid advisory approval fingerprint")
        reasons.append("UNTRUSTED_APPROVAL_CANNOT_AUTHORIZE")
    reasons = tuple(sorted(set(reasons)))
    return PlanPolicyDecision(
        digest, problem.digest(),
        "PURE_SYNTHETIC_PREVIEW_ONLY" if not reasons else "HOLD_POLICY_DENIED",
        reasons, tuple(step[0] for step in plan.steps) if not reasons else ())


def assert_pure_preview(
    problem: ProblemSpec, plan: PlanSpec, policy: PlanPolicyDecision,
) -> None:
    """Re-evaluate rather than trust a caller-built policy dataclass."""
    if type(policy) is not PlanPolicyDecision:
        raise ValueError("typed plan policy required")
    fresh = evaluate_plan_policy(problem, plan)
    if (fresh.disposition != "PURE_SYNTHETIC_PREVIEW_ONLY"
            or policy != fresh):
        raise PermissionError("untrusted or denied plan policy")


# EAI P1 SWU 027: complete Problem/Plan -> local review gate without GO.
def evaluate_problem_review_policy(
    problem: ProblemSpec, plan: PlanSpec, *,
    architect_truth: str,
    evidence_review_required: bool = False,
    proposed_approval_hash: str | None = None,
) -> PlanPolicyDecision:
    """Separate truth/negative evidence from executable approval.

    Even an advisory architect result may only reach the existing pure
    synthetic no-op preview, never a real tool or authorization transition.
    """
    if (type(architect_truth) is not str or
            architect_truth not in ("UNVERIFIED", "CONFLICT", "UNSUPPORTED")):
        raise ValueError("untrusted architect truth status")
    if type(evidence_review_required) is not bool:
        raise ValueError("explicit evidence review flag required")
    base = evaluate_plan_policy(
        problem, plan, proposed_approval_hash=proposed_approval_hash)
    reasons = set(base.reason_codes)
    if architect_truth != "UNVERIFIED":
        reasons.add("ARCHITECT_TRUTH_NOT_REVIEWABLE")
    if evidence_review_required:
        reasons.add("NEGATIVE_OR_CONFLICTED_EVIDENCE")
    # Explicitly deny ambiguous constraints which an input parser cannot prove.
    for clause in _validated_problem(problem).hard_constraints:
        if re.fullmatch(r"(?:must|forbid):[a-z][a-z0-9_.-]{0,63}", clause) is None:
            reasons.add("UNMODELED_HARD_CONSTRAINT")
    if reasons:
        return PlanPolicyDecision(
            base.plan_sha256, base.problem_sha256, "HOLD_POLICY_DENIED",
            tuple(sorted(reasons)), ())
    return base
