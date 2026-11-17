"""Independent CPU comparison of actually interpreted synthetic AXNODE outputs.

Candidate output hashes are compared to the existing, separately implemented
read-only CSV CPU solver on disposable synthetic data. No model-generated
receipt, user-supplied status or own witness can grant VERIFIED/ACTIVE rights.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec, canonical_bytes
from .logic_oracle import SyntheticComparison, _records
from .logic_synthesis import SynthesisCandidate
from .synthetic_candidate_interpreter import (
    SyntheticCandidateExecution, SyntheticStepWitness, SyntheticFamilyWitness,
)
from .solver_reference_check import compare_real_cpu_on_synthetic, _expected


@dataclass(frozen=True)
class SyntheticCandidateReceipt:
    status: str
    candidate_sha256: str
    problem_sha256: str
    witness_sha256: str
    checked_families: tuple[str, ...]
    counterexample_families: tuple[str, ...]
    independent_cpu_executed: bool
    interpretation_executed: bool
    real_world_verified: bool = False
    permits_promotion: bool = False
    permits_learning: bool = False


def verify_synthetic_interpretation(
        store: AXNodeStore, problem: ProblemSpec,
        candidate: SynthesisCandidate,
        fixtures: tuple[SyntheticComparison, ...],
        witness: SyntheticCandidateExecution) -> SyntheticCandidateReceipt:
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec or
            type(candidate) is not SynthesisCandidate or
            type(fixtures) is not tuple or
            type(witness) is not SyntheticCandidateExecution):
        raise ValueError("explicit typed synthetic witness required")
    if not 2 <= len(fixtures) <= 12:
        raise ValueError("synthetic verifier fixture budget exceeded")
    if (witness.disposition != "SYNTHETIC_INTERPRETED_UNVERIFIED" or
            witness.problem_sha256 != problem.digest() or
            witness.candidate_sha256 != candidate.candidate_sha256 or
            witness.real_world_verified or witness.permits_promotion or
            witness.permits_external_action or
            not witness.sandbox_candidate_interpreted or
            len(witness.steps) != len(candidate.node_hashes) or
            len(witness.families) != len(fixtures)):
        return SyntheticCandidateReceipt(
            "REJECTED_INVALID_SYNTHETIC_WITNESS",
            candidate.candidate_sha256, problem.digest(), witness.witness_sha256,
            (), (), False, False)
    for i, step in enumerate(witness.steps):
        if (type(step) is not SyntheticStepWitness or
                step.node_sha256 != candidate.node_hashes[i] or
                step.output_type != "difference_receipt" or
                type(step.step_index) is not int or step.step_index != i):
            return SyntheticCandidateReceipt(
                "REJECTED_INVALID_SYNTHETIC_WITNESS",
                candidate.candidate_sha256, problem.digest(), witness.witness_sha256,
                (), (), False, False)
        node = store.get(step.node_sha256).as_dict()
        if (node["signature"]["output"] != "difference_receipt" or
                len(node["steps"]) != 1 or
                node["steps"][0]["skill"] != "csv.reconcile.v1" or
                (i and "difference_receipt" not in
                 node["signature"]["inputs"].values())):
            return SyntheticCandidateReceipt(
                "REJECTED_UNSUPPORTED_CANDIDATE_SEMANTICS",
                candidate.candidate_sha256, problem.digest(), witness.witness_sha256,
                (), (), False, False)
    serialized = {
        "schema": "eai.synthetic.candidate.execution.v1",
        "problem_sha256": problem.digest(),
        "candidate_sha256": candidate.candidate_sha256,
        "steps": [[s.node_sha256, s.output_type, s.step_index]
                  for s in witness.steps],
        "families": [[f.family, f.difference_sha256,
                      f.difference_count, f.executed_steps]
                     for f in witness.families],
    }
    expected_witness_hash = hashlib.sha256(canonical_bytes(serialized)).hexdigest()
    if expected_witness_hash != witness.witness_sha256:
        return SyntheticCandidateReceipt(
            "REJECTED_TAMPERED_SYNTHETIC_WITNESS",
            candidate.candidate_sha256, problem.digest(), witness.witness_sha256,
            (), (), False, False)
    # Each fixture is independently parsed and verified, not accepted from
    # the witness. Fail *before CPU execution* on malformed family or count.
    seen = set()
    for claim, fixture in zip(witness.families, fixtures):
        if (type(claim) is not SyntheticFamilyWitness or
                type(fixture) is not SyntheticComparison or
                claim.family != fixture.family or claim.family in seen or
                type(claim.difference_count) is not int or
                type(claim.executed_steps) is not int or
                claim.executed_steps != len(candidate.node_hashes) or
                not 0 <= claim.difference_count <= 48):
            return SyntheticCandidateReceipt(
                "REJECTED_INVALID_SYNTHETIC_FAMILY",
                candidate.candidate_sha256, problem.digest(), witness.witness_sha256,
                (), (), False, False)
        seen.add(claim.family)
    independent = compare_real_cpu_on_synthetic(fixtures)
    failed = []
    checked = []
    any_run = False
    for fixture, claimed, observed in zip(fixtures, witness.families, independent):
        any_run |= observed.baseline_executed
        if observed.verdict != "BASELINE_CPU_MATCH_UNVERIFIED":
            failed.append(fixture.family)
            continue
        # Structural raw counts are recomputed via the *reference* helper, not
        # pulled from the witness or from an AXNODE operator implementation.
        left, right = _records(fixture.left), _records(fixture.right)
        _status, _counts, reference_keys = _expected(left, right)
        if (observed.verified_difference_sha256 != claimed.difference_sha256 or
                len(reference_keys) != claimed.difference_count):
            failed.append(fixture.family)
        else:
            checked.append(fixture.family)
    return SyntheticCandidateReceipt(
        "SYNTHETIC_CANDIDATE_CPU_MATCH_UNVERIFIED" if not failed else
        "SYNTHETIC_CANDIDATE_COUNTEREXAMPLE_OR_INCONCLUSIVE",
        candidate.candidate_sha256, problem.digest(), witness.witness_sha256,
        tuple(checked), tuple(failed), any_run, True)
