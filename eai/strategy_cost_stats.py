"""EAI-SWU-026 bounded read-only local cost statistics for strategy ranks.

Declared and synthetic costs are not runtime measurements, verification,
out-of-distribution evidence or a learned capability upgrade.
"""
from __future__ import annotations

from dataclasses import dataclass

from .strategy_research_ranker import SyntheticStrategyScore


@dataclass(frozen=True)
class StrategyCostEnvelope:
    candidate_sha256: str
    step_upper_bound: int
    second_upper_bound: int
    synthetic_train_count: int
    synthetic_heldout_count: int
    research_cost_score: int
    status: str = "COST_ONLY_RESEARCH_UNVERIFIED"
    out_of_distribution_checked: bool = False
    permits_learning: bool = False
    measured_synthetic_cpu_ms: int | None = None
    cost_basis: str = "DECLARED_BUDGET_ONLY"


def build_bounded_strategy_cost_envelope(
    scored: tuple[SyntheticStrategyScore, ...],
    *, max_steps: int = 64, max_seconds: int = 300,
) -> tuple[StrategyCostEnvelope, ...]:
    if (type(scored) is not tuple or len(scored) > 4
            or type(max_steps) is not int or not 1 <= max_steps <= 64
            or type(max_seconds) is not int or not 1 <= max_seconds <= 300):
        raise ValueError("typed limited strategy cost inputs required")
    result = []
    seen = set()
    for item in scored:
        if (type(item) is not SyntheticStrategyScore
                or item.candidate_sha256 in seen
                or item.trusted_for_learning
                or item.review_status != "B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED"
                or type(item.declared_steps) is not int
                or type(item.declared_seconds) is not int
                or not 1 <= item.declared_steps <= max_steps
                or not 1 <= item.declared_seconds <= max_seconds
                or type(item.compared_train) is not int
                or type(item.compared_heldout) is not int
                or not 1 <= item.compared_train <= 32
                or not 1 <= item.compared_heldout <= 32
                or (item.measured_synthetic_cpu_ms is not None and (
                    type(item.measured_synthetic_cpu_ms) is not int
                    or not 0 <= item.measured_synthetic_cpu_ms <= max_seconds * 1000))):
            raise ValueError("untrusted or over-budget strategy cost")
        seen.add(item.candidate_sha256)
        result.append(StrategyCostEnvelope(
            item.candidate_sha256, item.declared_steps,
            item.declared_seconds, item.compared_train,
            item.compared_heldout,
            item.declared_seconds + 2 * item.declared_steps,
            measured_synthetic_cpu_ms=item.measured_synthetic_cpu_ms,
            cost_basis=("OBSERVED_SYNTHETIC_PROCESS_CPU_ONLY"
                        if item.measured_synthetic_cpu_ms is not None
                        else "DECLARED_BUDGET_ONLY")))
    return tuple(sorted(result, key=lambda x: (
        0 if x.measured_synthetic_cpu_ms is not None else 1,
        x.measured_synthetic_cpu_ms
        if x.measured_synthetic_cpu_ms is not None else 300001,
        x.research_cost_score, x.step_upper_bound,
        x.candidate_sha256)))
