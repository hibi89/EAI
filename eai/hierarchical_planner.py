"""Bounded, non-executing V3-06 plan DAG from pinned candidate AXNODEs.

This module NEVER invokes a skill, promotes an AXNODE or marks a receipt verified.
Only operators already allowed by PlanSpec are represented as *proposed* steps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .axnode_store import AXNodeStore
from .contracts import PlanSpec, ProblemSpec
from .design_engine import DesignOutcome
from .strategy_cost import rank_plan_costs

_SUPPORTED = frozenset({
    "synthetic.noop.v1",
    "csv.reconcile.v1",
    "evidence.verify_receipt.v1",
})


@dataclass(frozen=True)
class PlanCandidate:
    alternative_id: str
    plan: PlanSpec
    node_hashes: tuple[str, ...]
    step_sources: tuple[tuple[str, str], ...]
    declared_step_count: int
    declared_seconds_upper_bound: int
    trust: str = "ADVISORY_UNVERIFIED_NOT_EXECUTED"


@dataclass(frozen=True)
class PlanningOutcome:
    problem_sha256: str
    candidates: tuple[PlanCandidate, ...]
    blocked: tuple[tuple[str, str], ...]
    status: str
    expansions: int


class HierarchicalPlanner:
    """Builds tiny deterministic subgoal dependency graphs, no tool execution."""

    def __init__(self, store: AXNodeStore):
        if type(store) is not AXNodeStore:
            raise ValueError("explicit local AXNODE store required")
        self._store = store

    def plan(self, problem: ProblemSpec, design: DesignOutcome, *,
             max_expansions: int = 8, cancelled: Callable[[], bool] | None = None
             ) -> PlanningOutcome:
        if type(problem) is not ProblemSpec or type(design) is not DesignOutcome:
            raise ValueError("typed problem and design required")
        if type(max_expansions) is not int or not 1 <= max_expansions <= 8:
            raise ValueError("invalid bounded search budget")
        if cancelled is not None and not callable(cancelled):
            raise ValueError("invalid cancellation callback")
        digest = problem.digest()
        if (design.analysis.problem_sha256 != digest or
                design.design.problem_sha256 != digest or
                design.result.problem_sha256 != digest):
            raise ValueError("cross-problem plan reuse denied")
        if design.design.blocked_reason or not design.design.alternatives:
            return PlanningOutcome(digest, (), (("design", "DESIGN_BLOCKED"),),
                                   "BLOCKED", 0)
        if design.result.status not in ("UNVERIFIED", "UNSUPPORTED"):
            return PlanningOutcome(digest, (), (("design", "UNTRUSTED_RESULT_STATUS"),),
                                   "BLOCKED", 0)
        if problem.risk == "HIGH" or design.analysis.contradictions:
            return PlanningOutcome(digest, (), (("design", "REQUIRES_INDEPENDENT_REVIEW"),),
                                   "BLOCKED", 0)
        candidates: list[PlanCandidate] = []
        blocked: list[tuple[str, str]] = []
        known = {item.strategy_id: item for item in design.analysis.evidence}
        expansions = 0
        for alternative_id, refs, _tradeoffs, _verification in design.design.alternatives:
            if cancelled is not None and cancelled():
                return PlanningOutcome(digest, tuple(candidates), tuple(blocked),
                                       "CANCELLED", expansions)
            if expansions >= max_expansions:
                blocked.append((alternative_id, "SEARCH_BUDGET_REACHED"))
                continue
            expansions += 1
            try:
                if (not refs or len(refs) > 8 or len(refs) != len(set(refs)) or
                        not set(design.analysis.required).issubset(refs) or
                        set(refs).intersection(design.analysis.forbidden)):
                    raise ValueError("STRATEGY_CONSTRAINT_MISMATCH")
                nodes_by_hash = {}
                for ref in refs:
                    pinned = known.get(ref)
                    if pinned is None or pinned.status != "UNVERIFIED":
                        raise ValueError("UNPINNED_CANDIDATE")
                    node = self._store.get(pinned.source_sha256)
                    raw = node.as_dict()
                    if (node.sha256 != pinned.source_sha256 or raw["id"] != ref or
                            raw["status"] not in ("DRAFT", "CANDIDATE")):
                        raise ValueError("CANDIDATE_SOURCE_MISMATCH")
                    nodes_by_hash[node.sha256] = raw
                if len(nodes_by_hash) != len(refs):
                    raise ValueError("DUPLICATE_STRATEGY_HASH")
                # Kahn-style bounded DAG order. Parents not included in a
                # proposed plan cannot be silently pulled into execution.
                ordered = []
                remaining = set(nodes_by_hash)
                while remaining:
                    ready = sorted(
                        (h for h in remaining
                         if set(nodes_by_hash[h]["parent_hashes"]).issubset(
                             set(nodes_by_hash) - remaining)),
                        key=lambda h: (nodes_by_hash[h]["id"], h),
                    )
                    if not ready:
                        raise ValueError("MISSING_OR_CYCLIC_NODE_PARENT")
                    for h in ready:
                        for p in nodes_by_hash[h]["parent_hashes"]:
                            if (nodes_by_hash[p]["signature"]["output"] not in
                                    nodes_by_hash[h]["signature"]["inputs"].values()):
                                raise ValueError("INCOMPATIBLE_PARENT_OUTPUT_TYPE")
                        ordered.append(h)
                        remaining.remove(h)
                steps: list[dict] = []
                sources = []
                tail: dict[str, str] = {}
                seconds = 0
                for h in ordered:
                    raw = nodes_by_hash[h]
                    seconds += raw["budget"]["max_seconds"]
                    prev = None
                    for step in raw["steps"]:
                        operator = step["skill"]
                        if operator not in _SUPPORTED:
                            raise ValueError("UNSUPPORTED_PLAN_OPERATOR")
                        capability = ("local.read" if operator == "csv.reconcile.v1"
                                      else "pure")
                        if (capability == "local.read" and
                                ("local.read" not in problem.permissions or
                                 "local.read" not in raw["capabilities"])):
                            raise ValueError("PLAN_CAPABILITY_NOT_AUTHORIZED")
                        deps = [tail[p] for p in raw["parent_hashes"]] if prev is None else [prev]
                        sid = "step" + str(len(steps) + 1).zfill(2)
                        steps.append({"id": sid, "operator": operator,
                                      "requires": sorted(set(deps)),
                                      "capability": capability})
                        sources.append((sid, h))
                        prev = sid
                    if prev is None:
                        raise ValueError("EMPTY_NODE_PLAN")
                    tail[h] = prev
                if len(steps) > problem.budget[0] or seconds > problem.budget[1]:
                    raise ValueError("PLAN_RESOURCE_BUDGET_EXCEEDED")
                plan = PlanSpec.validate({
                    "version": 1, "problem_sha256": digest, "steps": steps,
                    "budget": {"max_steps": problem.budget[0],
                               "max_seconds": problem.budget[1]},
                })
                candidates.append(PlanCandidate(alternative_id, plan, tuple(ordered),
                                                tuple(sources), len(steps), seconds))
            except (KeyError, ValueError) as exc:
                code = str(exc) if isinstance(exc, ValueError) and str(exc) in {
                    "STRATEGY_CONSTRAINT_MISMATCH", "UNPINNED_CANDIDATE",
                    "CANDIDATE_SOURCE_MISMATCH", "DUPLICATE_STRATEGY_HASH",
                    "MISSING_OR_CYCLIC_NODE_PARENT", "INCOMPATIBLE_PARENT_OUTPUT_TYPE",
                    "UNSUPPORTED_PLAN_OPERATOR", "PLAN_CAPABILITY_NOT_AUTHORIZED",
                    "PLAN_RESOURCE_BUDGET_EXCEEDED",
                } else "CANDIDATE_INTEGRITY_OR_CONTRACT_FAILURE"
                blocked.append((alternative_id, code))
        try:
            candidates = list(rank_plan_costs(
                candidates, max_steps=problem.budget[0],
                max_seconds=problem.budget[1], cancelled=cancelled))
        except ValueError as exc:
            if str(exc) != "planning cost ranking cancelled":
                raise
            return PlanningOutcome(digest, (), tuple(blocked),
                                   "CANCELLED", expansions)
        status = ("CANDIDATES_UNVERIFIED" if len(candidates) >= 2 else
                  "PARTIAL_UNVERIFIED" if candidates else "BLOCKED")
        return PlanningOutcome(digest, tuple(candidates), tuple(blocked),
                               status, expansions)


# EAI-SWU-015: actual plan candidates -> source-pinned advisory decision.
@dataclass(frozen=True)
class HierarchicalPlanReview:
    problem_sha256: str
    status: str
    selected_alternative_id: str | None
    selected_plan: PlanSpec | None
    selected_step_sources: tuple[tuple[str, str], ...]
    alternatives: tuple[str, ...]
    blocked: tuple[tuple[str, str], ...]
    reason_codes: tuple[str, ...]
    expansions: int
    can_execute_real_actions: bool = False
    independent_verification: str = "NOT_ESTABLISHED"


def plan_and_review_provenance(
    planner: HierarchicalPlanner, problem: ProblemSpec,
    design: DesignOutcome, *, max_expansions: int = 8,
    cancelled: Callable[[], bool] | None = None,
) -> HierarchicalPlanReview:
    """Design→bounded DAG→pinned step sources→EAI-owned advisory or abstain."""
    if type(planner) is not HierarchicalPlanner or type(problem) is not ProblemSpec:
        raise ValueError("explicit local planner and problem required")
    outcome = planner.plan(
        problem, design, max_expansions=max_expansions, cancelled=cancelled)
    if outcome.problem_sha256 != problem.digest():
        raise ValueError("planner outcome crossed problem identity")
    alternatives = tuple(c.alternative_id for c in outcome.candidates)
    if len(set(alternatives)) != len(alternatives) or len(alternatives) > 8:
        raise ValueError("invalid bounded planner alternatives")
    blockers = list(outcome.blocked)
    for candidate in outcome.candidates:
        if candidate.trust != "ADVISORY_UNVERIFIED_NOT_EXECUTED":
            raise ValueError("untrusted plan authority")
        if candidate.plan.problem_sha256 != problem.digest():
            raise ValueError("cross-problem candidate plan")
        step_ids = tuple(sid for sid, *_ in candidate.plan.steps)
        if len(candidate.step_sources) != len(step_ids) or (
                tuple(sid for sid, _ in candidate.step_sources) != step_ids):
            raise ValueError("unbound plan steps")
        if (len(candidate.node_hashes) > 8 or
                len(set(candidate.node_hashes)) != len(candidate.node_hashes)
                or any(h not in candidate.node_hashes for _, h in candidate.step_sources)):
            raise ValueError("unbound AXNODE source")
        for digest in candidate.node_hashes:
            if planner._store.get(digest).sha256 != digest:
                raise ValueError("stale AXNODE source in plan")
    if outcome.status == "CANCELLED":
        return HierarchicalPlanReview(
            problem.digest(), "CANCELLED", None, None, (),
            alternatives, tuple(blockers), ("CANCELLED_BEFORE_DECISION",),
            outcome.expansions)
    if outcome.status not in ("CANDIDATES_UNVERIFIED", "PARTIAL_UNVERIFIED", "BLOCKED"):
        raise ValueError("unexpected local plan search disposition")
    # One candidate is not silently sold as a reviewed alternative choice.
    if (outcome.status != "CANDIDATES_UNVERIFIED"
            or len(outcome.candidates) < 2
            or design.design.blocked_reason or design.analysis.contradictions):
        reasons = tuple(sorted({
            "ALTERNATIVES_NOT_ESTABLISHED",
            *(reason for _aid, reason in blockers),
        }))
        return HierarchicalPlanReview(
            problem.digest(), "ABSTAINED", None, None, (),
            alternatives, tuple(blockers), reasons, outcome.expansions)
    chosen = outcome.candidates[0]
    return HierarchicalPlanReview(
        problem.digest(), "ADVISORY_PLAN_NOT_EXECUTED",
        chosen.alternative_id, chosen.plan, chosen.step_sources,
        alternatives, tuple(blockers),
        ("INDEPENDENT_ORACLE_REQUIRED",), outcome.expansions)
