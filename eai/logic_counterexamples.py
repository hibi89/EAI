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


# EAI-SWU-019: bounded rewrite only after a rejected structural candidate.
@dataclass(frozen=True)
class SynthesisRevision:
    status: str
    previous_sha256: str
    proposed_sha256: str | None
    revised_candidate: SynthesisCandidate | None
    declarative_program_sha256: str | None
    checked_variants: int
    reason_codes: tuple[str, ...]
    independent_semantic_proof: bool = False
    permits_execution: bool = False
    permits_promotion: bool = False


def revise_rejected_synthesis(
    synthesizer, verifier: StructuralVerifier, problem: ProblemSpec,
    rejected: SynthesisCandidate, alternative_node_hashes: tuple[str, ...] = (),
    *, max_variants: int = 64,
) -> SynthesisRevision:
    """A failed structural receipt can trigger a bounded candidate revision.

    Valid structural proposals and failing semantic ideas are NOT proof; this
    function repairs only syntactic/typed chains, with no store modifications.
    """
    from itertools import permutations
    from .logic_synthesis import LogicSynthesizer, compile_bounded_composition
    if (type(synthesizer) is not LogicSynthesizer
            or type(verifier) is not StructuralVerifier
            or synthesizer.store is not verifier.store
            or type(problem) is not ProblemSpec
            or type(rejected) is not SynthesisCandidate
            or type(alternative_node_hashes) is not tuple
            or len(alternative_node_hashes) > 8
            or type(max_variants) is not int or not 1 <= max_variants <= 64):
        raise ValueError("bounded typed synthesis revision inputs required")
    current = verifier.check(problem, rejected)
    if current.status != "REJECTED_UNVERIFIED":
        if current.status != "STRUCTURE_ONLY_UNVERIFIED":
            raise ValueError("unexpected structural verifier disposition")
        audit = probe_structural_counterexamples(verifier, problem, rejected)
        return SynthesisRevision(
            "HOLD_VERIFIER_GAP" if audit.accepted_forged_cases else
            "NO_REJECTED_CANDIDATE", rejected.candidate_sha256,
            None, None, None, 0,
            ("COUNTEREXAMPLE_ACCEPTED",) if audit.accepted_forged_cases else
            ("NO_STRUCTURAL_FAILURE",))
    pool = tuple(dict.fromkeys(
        (*rejected.node_hashes, *alternative_node_hashes)))
    if len(pool) > 8 or any(
            type(d) is not str or len(d) != 64 or
            any(ch not in "0123456789abcdef" for ch in d) for d in pool):
        raise ValueError("invalid bounded candidate node pool")
    tried = 0
    # Preserve original length first; then bounded linear 2..4 candidates.
    sizes = tuple(dict.fromkeys((
        min(4, max(2, len(rejected.node_hashes))), 2, 3, 4)))
    for size in sizes:
        if size > len(pool):
            continue
        for combination in permutations(pool, size):
            if tried >= max_variants:
                break
            tried += 1
            try:
                candidate = synthesizer.compose(problem, combination)
                if candidate.candidate_sha256 == rejected.candidate_sha256:
                    continue
                check = verifier.check(problem, candidate)
                if check.status != "STRUCTURE_ONLY_UNVERIFIED":
                    continue
                adversarial = probe_structural_counterexamples(
                    verifier, problem, candidate)
                if adversarial.accepted_forged_cases:
                    return SynthesisRevision(
                        "HOLD_VERIFIER_GAP", rejected.candidate_sha256,
                        None, None, None, tried, ("COUNTEREXAMPLE_ACCEPTED",))
                program = compile_bounded_composition(
                    synthesizer, problem, combination)
            except (ValueError, KeyError, TypeError, OSError):
                continue
            return SynthesisRevision(
                "STRUCTURAL_REVISION_UNVERIFIED",
                rejected.candidate_sha256, candidate.candidate_sha256,
                candidate, program.program_sha256, tried,
                ("SEMANTIC_ORACLE_NOT_RUN", "OWNER_PROMOTION_HOLD"))
        if tried >= max_variants:
            break
    return SynthesisRevision(
        "NO_SAFE_STRUCTURAL_REVISION", rejected.candidate_sha256,
        None, None, None, tried, ("NO_BOUNDED_VALID_TYPED_CHAIN",))
