"""Adversarial mutation checks for local structural candidate verification.

This cannot prove semantic correctness or safe action authority. It only
detects verifier acceptance of known-forged structural candidates.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .contracts import ProblemSpec
from .logic_synthesis import SynthesisCandidate
from .logic_verifier import StructuralVerifier


@dataclass(frozen=True)
class CounterexampleReview:
    status: str
    tested_cases: tuple[str, ...]
    accepted_forged_cases: tuple[str, ...]
    semantic_verified: bool = False
    permits_promotion: bool = False


def probe_structural_counterexamples(
        verifier: StructuralVerifier, problem: ProblemSpec,
        candidate: SynthesisCandidate, *, max_cases: int = 4
        ) -> CounterexampleReview:
    if (type(verifier) is not StructuralVerifier or
            type(problem) is not ProblemSpec or
            type(candidate) is not SynthesisCandidate or
            type(max_cases) is not int or not 1 <= max_cases <= 4):
        raise ValueError("typed, bounded counterexample check required")
    original = verifier.check(problem, candidate)
    if original.status != "STRUCTURE_ONLY_UNVERIFIED":
        return CounterexampleReview("BASELINE_STRUCTURAL_REJECTED", (), ())
    cases = (
        ("wrong_hash", replace(candidate, candidate_sha256="0" * 64)),
        ("fake_authority", replace(candidate, trust="VERIFIED")),
        ("tampered_steps", replace(candidate, step_count=candidate.step_count + 1)),
        ("reversed_lineage", replace(
            candidate, node_hashes=tuple(reversed(candidate.node_hashes)))),
    )[:max_cases]
    accepted = []
    tested = []
    for label, mutant in cases:
        receipt = verifier.check(problem, mutant)
        tested.append(label)
        if receipt.status != "REJECTED_UNVERIFIED":
            accepted.append(label)
    return CounterexampleReview(
        "STRUCTURAL_VERIFIER_GAP" if accepted else
        "NO_STRUCTURAL_COUNTEREXAMPLE_FOUND_UNVERIFIED",
        tuple(tested), tuple(accepted),
    )
