"""C17 research-only strategy ranking after recomputed B0/B1 synthetic checks.

There is intentionally NO persistent trained learner and NO ACTIVE change:
unverified synthetic parity cannot be elevated into a trusted reward signal.
The chosen order minimizes declared CPU cost only among eligible simulations.
"""
from __future__ import annotations

from dataclasses import dataclass

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec
from .logic_synthesis import LogicSynthesizer, SynthesisCandidate
from .synthetic_candidate_benchmark import benchmark_synthetic_candidate
from .synthetic_curriculum import SyntheticCurriculum, generate_synthetic_curriculum


@dataclass(frozen=True)
class SyntheticStrategyScore:
    candidate_sha256: str
    review_status: str
    compared_train: int
    compared_heldout: int
    declared_steps: int
    declared_seconds: int
    trusted_for_learning: bool = False


@dataclass(frozen=True)
class StrategyRankingPreview:
    disposition: str
    problem_sha256: str
    curriculum_sha256: str
    ranked: tuple[SyntheticStrategyScore, ...]
    held: tuple[tuple[str, str], ...]
    learner_trained: bool = False
    verified_uplift: str = "NOT_MEASURED"
    permits_promotion: bool = False
    permits_real_execution: bool = False


def rank_synthetic_strategy_previews(
    store: AXNodeStore, problem: ProblemSpec,
    candidates: tuple[SynthesisCandidate, ...],
    curriculum: SyntheticCurriculum,
) -> StrategyRankingPreview:
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec
            or type(candidates) is not tuple or not 1 <= len(candidates) <= 4
            or type(curriculum) is not SyntheticCurriculum):
        raise ValueError("explicit bounded synthetic strategy inputs required")
    if curriculum != generate_synthetic_curriculum(curriculum.seed):
        raise ValueError("forged or cross-split synthetic curriculum")
    if (any(type(c) is not SynthesisCandidate for c in candidates)
            or len({c.candidate_sha256 for c in candidates}) != len(candidates)):
        raise ValueError("untrusted or repeated candidate inventory")
    scored, held = [], []
    for candidate in candidates:
        try:
            rebuilt = LogicSynthesizer(store).compose(
                problem, candidate.node_hashes)
            if rebuilt != candidate:
                held.append((candidate.candidate_sha256,
                             "CANDIDATE_STRUCTURE_OR_HASH_CHANGED"))
                continue
            report = benchmark_synthetic_candidate(
                store, problem, candidate, curriculum.train, curriculum.heldout)
            valid = (
                report.status == "B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED"
                and report.candidate_sha256 == candidate.candidate_sha256
                and report.train_count == len(curriculum.train)
                and report.heldout_count == len(curriculum.heldout)
                and report.b0_train_matches == len(curriculum.train)
                and report.b0_heldout_matches == len(curriculum.heldout)
                and report.b1_train_compared == len(curriculum.train)
                and report.b1_heldout_compared == len(curriculum.heldout)
                and report.external_truth_verified is False
                and report.permission_to_learn is False
                and report.permission_to_promote is False
                and report.measured_runtime_uplift == "NOT_MEASURED"
            )
            if not valid:
                held.append((candidate.candidate_sha256,
                             "INDEPENDENT_SYNTHETIC_PARITY_NOT_ESTABLISHED"))
                continue
            scored.append(SyntheticStrategyScore(
                candidate.candidate_sha256, report.status,
                report.b1_train_compared, report.b1_heldout_compared,
                candidate.step_count, candidate.predicted_seconds))
        except (ValueError, KeyError):
            held.append((candidate.candidate_sha256,
                         "SYNTHETIC_CANDIDATE_RECHECK_REJECTED"))
    scored.sort(key=lambda item: (
        item.declared_seconds, item.declared_steps, item.candidate_sha256))
    return StrategyRankingPreview(
        "SYNTHETIC_COST_ORDER_ONLY_NOT_LEARNING" if scored
        else "HOLD_NO_RECHECKED_SYNTHETIC_STRATEGY",
        problem.digest(), curriculum.manifest_sha256,
        tuple(scored), tuple(held))
