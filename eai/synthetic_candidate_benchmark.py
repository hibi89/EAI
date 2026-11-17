"""B0 vs bounded B1 on isolated synthetic train/heldout families.

B0 runs existing legacy read-only CPU reconciliation; B1 interprets newly
composed AXNODE steps and has its outputs independently checked by B0.
Synthetic parity is NOT verified uplift or proof on unseen real-world tasks.
"""
from __future__ import annotations

from dataclasses import dataclass

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec
from .logic_oracle import SyntheticComparison
from .logic_synthesis import SynthesisCandidate
from .synthetic_holdout import compare_b0_train_and_heldout
from .synthetic_candidate_interpreter import interpret_synthetic_candidate
from .synthetic_candidate_verifier import verify_synthetic_interpretation


@dataclass(frozen=True)
class SyntheticB1Benchmark:
    status: str
    train_count: int
    heldout_count: int
    b0_train_matches: int
    b0_heldout_matches: int
    b1_train_compared: int
    b1_heldout_compared: int
    candidate_sha256: str
    baseline_sha256: str = "LEGACY_RECONCILE_CSV_UNPINNED"
    measured_runtime_uplift: str = "NOT_MEASURED"
    external_truth_verified: bool = False
    permission_to_learn: bool = False
    permission_to_promote: bool = False


def benchmark_synthetic_candidate(
        store: AXNodeStore, problem: ProblemSpec,
        candidate: SynthesisCandidate,
        train: tuple[SyntheticComparison, ...],
        heldout: tuple[SyntheticComparison, ...]) -> SyntheticB1Benchmark:
    if type(store) is not AXNodeStore or type(problem) is not ProblemSpec or type(candidate) is not SynthesisCandidate:
        raise ValueError("typed bounded AXNODE benchmark required")
    b0 = compare_b0_train_and_heldout(
        store, problem, candidate, train, heldout)
    if b0.status != "B0_SYNTHETIC_HELDOUT_MATCH_UNVERIFIED":
        return SyntheticB1Benchmark(
            "HOLD_B0_UNVERIFIED_OR_LEAK", len(train), len(heldout),
            b0.training_cpu_matches, b0.heldout_cpu_matches, 0, 0,
            candidate.candidate_sha256)
    try:
        train_execution = interpret_synthetic_candidate(
            store, problem, candidate, train)
        checked_train = verify_synthetic_interpretation(
            store, problem, candidate, train, train_execution)
    except ValueError:
        return SyntheticB1Benchmark(
            "HOLD_B1_SYNTHETIC_INTERPRETER_UNSUPPORTED", len(train),
            len(heldout), b0.training_cpu_matches, b0.heldout_cpu_matches,
            0, 0, candidate.candidate_sha256)
    if checked_train.status != "SYNTHETIC_CANDIDATE_CPU_MATCH_UNVERIFIED":
        return SyntheticB1Benchmark(
            "HOLD_B1_TRAIN_COUNTEREXAMPLE", len(train),
            len(heldout), b0.training_cpu_matches, b0.heldout_cpu_matches,
            len(checked_train.checked_families), 0, candidate.candidate_sha256)
    heldout_execution = interpret_synthetic_candidate(
        store, problem, candidate, heldout)
    checked_heldout = verify_synthetic_interpretation(
        store, problem, candidate, heldout, heldout_execution)
    status = (
        "B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED"
        if checked_heldout.status == "SYNTHETIC_CANDIDATE_CPU_MATCH_UNVERIFIED"
        and len(checked_heldout.checked_families) == len(heldout)
        else "HOLD_B1_HELDOUT_COUNTEREXAMPLE")
    return SyntheticB1Benchmark(
        status, len(train), len(heldout),
        b0.training_cpu_matches, b0.heldout_cpu_matches,
        len(checked_train.checked_families),
        len(checked_heldout.checked_families),
        candidate.candidate_sha256)
