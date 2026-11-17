"""Deterministic local plan cost ordering, not learned accuracy or execution."""
from __future__ import annotations

from typing import Callable


def rank_plan_costs(candidates: list, *, max_steps: int,
                    max_seconds: int,
                    cancelled: Callable[[], bool] | None = None) -> tuple:
    """Lower worst-case CPU time + bounded per-step overhead ranks first."""
    from .hierarchical_planner import PlanCandidate
    if (type(candidates) is not list or len(candidates) > 8
            or type(max_steps) is not int or not 1 <= max_steps <= 64
            or type(max_seconds) is not int or not 1 <= max_seconds <= 300
            or cancelled is not None and not callable(cancelled)):
        raise ValueError("invalid bounded planning cost input")
    ranked = []
    for candidate in candidates:
        if cancelled is not None:
            stopping = cancelled()
            if type(stopping) is not bool:
                raise ValueError("cancellation callback must be boolean")
            if stopping:
                raise ValueError("planning cost ranking cancelled")
        if (type(candidate) is not PlanCandidate
                or candidate.trust != "ADVISORY_UNVERIFIED_NOT_EXECUTED"
                or type(candidate.declared_step_count) is not int
                or type(candidate.declared_seconds_upper_bound) is not int
                or not 1 <= candidate.declared_step_count <= max_steps
                or not 1 <= candidate.declared_seconds_upper_bound <= max_seconds
                or len(candidate.plan.steps) != candidate.declared_step_count):
            raise ValueError("untrusted cost candidate")
        # Conservative fixed 2 CPU seconds/step overhead; not measured latency.
        estimated = candidate.declared_seconds_upper_bound + (
            2 * candidate.declared_step_count)
        ranked.append((estimated, candidate.declared_step_count,
                       candidate.alternative_id, candidate))
    return tuple(entry[3] for entry in sorted(ranked, key=lambda x: x[:3]))
