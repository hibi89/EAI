"""C14 staged verification boundary: structure -> adversarial -> synthetic oracle.

All decisions are *review proposals*. There is no database mutation, status
promotion, skill execution, independent real-world truth or user consent.
"""
from __future__ import annotations

from dataclasses import dataclass

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec
from .logic_synthesis import SynthesisCandidate
from .logic_verifier import StructuralVerifier
from .logic_counterexamples import probe_structural_counterexamples
from .logic_oracle import SyntheticComparison, SyntheticReconciliationOracle


@dataclass(frozen=True)
class CandidateReview:
    candidate_sha256: str
    disposition: str
    structural_status: str
    adversarial_status: str
    synthetic_oracle_status: str
    counterexample_families: tuple[str, ...]
    node_promotion: str = "FORBIDDEN_UNVERIFIED"
    execution: str = "FORBIDDEN_UNVERIFIED"
    independent_real_world_oracle: bool = False


def review_synthesis_candidate(
        store: AXNodeStore, problem: ProblemSpec,
        candidate: SynthesisCandidate,
        fixtures: tuple[SyntheticComparison, ...]) -> CandidateReview:
    """Pure bounded nonexecuting evaluation against caller-supplied synthetic claims."""
    if (type(store) is not AXNodeStore or
            type(problem) is not ProblemSpec or
            type(candidate) is not SynthesisCandidate or
            type(fixtures) is not tuple):
        raise ValueError("explicit typed candidate evaluation required")
    verifier = StructuralVerifier(store)
    baseline = verifier.check(problem, candidate)
    if baseline.status != "STRUCTURE_ONLY_UNVERIFIED":
        return CandidateReview(
            candidate.candidate_sha256, "QUARANTINE_REVIEW_REQUIRED",
            baseline.status, "NOT_RUN", "NOT_RUN", ())
    adversarial = probe_structural_counterexamples(
        verifier, problem, candidate, max_cases=4)
    if (adversarial.status != "NO_STRUCTURAL_COUNTEREXAMPLE_FOUND_UNVERIFIED"
            or adversarial.accepted_forged_cases):
        return CandidateReview(
            candidate.candidate_sha256, "QUARANTINE_REVIEW_REQUIRED",
            baseline.status, adversarial.status, "NOT_RUN",
            adversarial.accepted_forged_cases)
    oracle = SyntheticReconciliationOracle(verifier).check(
        problem, candidate, fixtures)
    if oracle.status == "SYNTHETIC_COUNTEREXAMPLE_FOUND":
        disposition = "QUARANTINE_REVIEW_REQUIRED"
    elif oracle.status == "SYNTHETIC_CLAIMS_MATCH_UNVERIFIED":
        disposition = "SYNTHETIC_EVIDENCE_ONLY_NOT_PROMOTED"
    else:
        disposition = "HOLD_NOT_VALIDATED"
    return CandidateReview(
        candidate.candidate_sha256, disposition,
        baseline.status, adversarial.status, oracle.status,
        oracle.counterexamples)
