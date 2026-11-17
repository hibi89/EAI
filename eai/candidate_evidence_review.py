"""Independent, bounded C14/C16 evidence binding. Synthetic evidence is never authority.

A caller-provided receipt is untrusted. Re-run the independent verifier against
the exact problem, AXNODE chain and synthetic fixture family before review.
Neither matching digests nor a successful CPU comparison grant learning,
execution, VERIFIED or ACTIVE rights.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec, canonical_bytes
from .logic_oracle import SyntheticComparison
from .logic_synthesis import SynthesisCandidate
from .synthetic_candidate_interpreter import (
    SyntheticCandidateExecution, interpret_synthetic_candidate,
)
from .synthetic_candidate_verifier import (
    SyntheticCandidateReceipt, verify_synthetic_interpretation,
)


@dataclass(frozen=True)
class CandidateEvidenceReview:
    status: str
    problem_sha256: str
    candidate_sha256: str
    fixture_sha256: str
    review_sha256: str
    reason_codes: tuple[str, ...]
    counterexample_families: tuple[str, ...]
    permits_promotion: bool = False
    permits_learning: bool = False
    permits_real_execution: bool = False


def review_candidate_evidence(
    store: AXNodeStore, problem: ProblemSpec,
    candidate: SynthesisCandidate, fixtures: tuple[SyntheticComparison, ...],
    execution: SyntheticCandidateExecution, claimed: SyntheticCandidateReceipt,
) -> CandidateEvidenceReview:
    """Recompute from source inputs. Never trust an externally supplied receipt."""
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec
            or type(candidate) is not SynthesisCandidate
            or type(fixtures) is not tuple or not 2 <= len(fixtures) <= 12
            or type(execution) is not SyntheticCandidateExecution
            or type(claimed) is not SyntheticCandidateReceipt):
        raise ValueError("explicit bounded typed evidence required")
    # The independent verifier validates family uniqueness, exact candidate
    # structure, witness hashes and the disposable legacy CPU comparison.
    checked = verify_synthetic_interpretation(
        store, problem, candidate, fixtures, execution)
    family_payload = []
    for item in fixtures:
        if type(item) is not SyntheticComparison:
            raise ValueError("untrusted fixture type")
        family_payload.append([
            item.family, [list(row) for row in item.left],
            [list(row) for row in item.right], list(item.claimed_different),
        ])
    fixture_sha = hashlib.sha256(canonical_bytes({
        "schema": "eai.synthetic.fixture.binding.v1",
        "families": family_payload,
    })).hexdigest()
    reasons = []
    # The receipt's "executed" flag is not proof of actual interpreter use.
    # Execute the bounded candidate again on the same fixtures, rather than
    # accepting a claimant-created witness as execution provenance.
    replayed_witness_sha = None
    try:
        replay = interpret_synthetic_candidate(store, problem, candidate, fixtures)
        replayed_witness_sha = replay.witness_sha256
        if replay != execution:
            reasons.append("EXECUTION_WITNESS_NOT_REPRODUCIBLE")
    except (ValueError, KeyError):
        reasons.append("INDEPENDENT_SYNTHETIC_REPLAY_REJECTED")
    if claimed != checked:
        reasons.append("CLAIMED_RECEIPT_DIFFERS_FROM_INDEPENDENT_RECOMPUTATION")
    if (claimed.real_world_verified or claimed.permits_promotion
            or claimed.permits_learning):
        reasons.append("FORGED_RECEIPT_AUTHORITY")
    if (execution.real_world_verified or execution.permits_promotion
            or execution.permits_external_action):
        reasons.append("FORGED_EXECUTION_AUTHORITY")
    if checked.status != "SYNTHETIC_CANDIDATE_CPU_MATCH_UNVERIFIED":
        reasons.append("INDEPENDENT_CPU_OR_STRUCTURE_DID_NOT_MATCH")
    if not checked.independent_cpu_executed or not checked.interpretation_executed:
        reasons.append("REQUIRED_EXECUTION_EVIDENCE_MISSING")
    if len(checked.checked_families) != len(fixtures):
        reasons.append("INCOMPLETE_HELDOUT_FAMILY_COVERAGE")
    if checked.counterexample_families:
        reasons.append("COUNTEREXAMPLE_PRESENT")
    status = ("SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED" if not reasons
              else "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT")
    reasons = tuple(sorted(set(reasons)))
    payload = {
        "schema": "eai.candidate.evidence.review.v1",
        "problem_sha256": problem.digest(),
        "candidate_sha256": candidate.candidate_sha256,
        "nodes": list(candidate.node_hashes),
        "fixture_sha256": fixture_sha,
        "witness_sha256": execution.witness_sha256,
        "replayed_witness_sha256": replayed_witness_sha,
        "independent_status": checked.status,
        "checked_families": list(checked.checked_families),
        "counterexamples": list(checked.counterexample_families),
        "disposition": status,
        "reasons": list(reasons),
    }
    review_sha = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return CandidateEvidenceReview(
        status, problem.digest(), candidate.candidate_sha256,
        fixture_sha, review_sha, reasons, checked.counterexample_families)
