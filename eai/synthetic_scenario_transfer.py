"""Independent bounded synthetic scenario transfer before CPU research updates.

This checks new signed-negative and multikey fixture *types*, not merely a
renamed seed of existing training examples. Never authorizes model fitting,
real tools, ACTIVE status, or makes population-OOD claims.
"""
from dataclasses import dataclass

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec
from .logic_synthesis import SynthesisCandidate
from .synthetic_curriculum import (
    SyntheticCurriculum, generate_synthetic_curriculum,
    generate_synthetic_transfer_families,
)
from .synthetic_holdout import _fixture_hash
from .synthetic_candidate_benchmark import (
    SyntheticB1Benchmark, benchmark_synthetic_candidate,
)


@dataclass(frozen=True)
class SyntheticScenarioTransfer:
    candidate_sha256: str
    status: str
    challenge_families: int
    b0_checked: int
    b1_checked: int
    b1_unmatched: int
    scenario_types: tuple[str, ...]
    semantic_scope: str = "SYNTHETIC_SCENARIO_TRANSFER_NOT_GENERAL_OOD"
    independently_verified_real_world: bool = False
    permits_learning: bool = False
    permits_promotion: bool = False


def evaluate_synthetic_scenario_transfer(
        store: AXNodeStore, problem: ProblemSpec,
        candidate: SynthesisCandidate,
        curriculum: SyntheticCurriculum) -> SyntheticScenarioTransfer:
    """Re-run actual B0 and B1 on two genuinely different synthetic scenarios.

    Reconstruct the fixed curriculum to prevent forged train/heldout input.
    Any content overlap or false candidate witness fails closed before any
    cumulative research prior can be updated.
    """
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec
            or type(candidate) is not SynthesisCandidate
            or type(curriculum) is not SyntheticCurriculum
            or curriculum != generate_synthetic_curriculum(curriculum.seed)):
        raise ValueError("verified local synthetic curriculum required")
    challenge = generate_synthetic_transfer_families(curriculum.seed)
    full = curriculum.train + curriculum.heldout + challenge
    if (len({fixture.family for fixture in full}) != len(full)
            or len({_fixture_hash(fixture) for fixture in full}) != len(full)):
        raise ValueError("synthetic scenario transfer leakage or duplicate")
    report = benchmark_synthetic_candidate(
        store, problem, candidate, curriculum.train, challenge)
    supported = (
        type(report) is SyntheticB1Benchmark
        and report.baseline_sha256 == "LEGACY_RECONCILE_CSV_UNPINNED"
        and report.status == "B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED"
        and report.candidate_sha256 == candidate.candidate_sha256
        and report.train_count == len(curriculum.train)
        and report.heldout_count == len(challenge)
        and report.b0_train_matches == len(curriculum.train)
        and report.b0_heldout_matches == len(challenge)
        and report.b1_train_compared == len(curriculum.train)
        and report.b1_heldout_compared == len(challenge)
        and report.external_truth_verified is False
        and report.permission_to_learn is False
        and report.permission_to_promote is False
        and report.measured_runtime_uplift == "NOT_MEASURED"
    )
    return SyntheticScenarioTransfer(
        candidate.candidate_sha256,
        "SYNTHETIC_SCENARIO_TRANSFER_MATCH_UNVERIFIED"
        if supported else "HOLD_SYNTHETIC_SCENARIO_COUNTEREXAMPLE",
        len(challenge),
        report.b0_heldout_matches if type(report) is SyntheticB1Benchmark else 0,
        report.b1_heldout_compared if type(report) is SyntheticB1Benchmark else 0,
        len(challenge) - min(len(challenge), report.b1_heldout_compared)
        if type(report) is SyntheticB1Benchmark else len(challenge),
        ("negative_signed_decimals", "multiple_key_and_value_changes"))
