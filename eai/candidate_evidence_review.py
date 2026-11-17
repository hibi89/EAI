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


# EAI-SWU-020: external receipt is untrusted until local independent replay.
@dataclass(frozen=True)
class CandidateReceiptIntake:
    status: str
    candidate_sha256: str
    independent_review_sha256: str
    journal_entry_sha256: str | None
    reason_codes: tuple[str, ...]
    source_authenticated: bool = False
    verified_real_world: bool = False
    permits_learning: bool = False
    permits_execution: bool = False
    permits_promotion: bool = False


def intake_candidate_receipt_for_review(
    store: AXNodeStore, problem: ProblemSpec, candidate: SynthesisCandidate,
    fixtures: tuple[SyntheticComparison, ...],
    execution: SyntheticCandidateExecution, claimed: SyntheticCandidateReceipt,
    journal, *, record_locally: bool = False,
) -> CandidateReceiptIntake:
    """Recompute candidate effects, then optionally write only a quarantine log.

    A SHA and a caller-supplied receipt never authenticate the claim's sender.
    This API deliberately cannot assert an external verifier's authority.
    """
    from .candidate_review_journal import CandidateReviewJournal
    if (type(journal) is not CandidateReviewJournal or
            type(record_locally) is not bool):
        raise ValueError("typed existing isolated journal and explicit option required")
    if journal.path.is_relative_to(store.root) or (
            journal.path.is_symlink()
            or not journal.path.is_file()):
        raise ValueError("review journal must not be stored in live AXNODE root")
    review = review_candidate_evidence(
        store, problem, candidate, fixtures, execution, claimed)
    if review.status not in (
            "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED",
            "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT"):
        raise ValueError("unexpected independent CPU review status")
    if review.permits_promotion or review.permits_learning or review.permits_real_execution:
        raise PermissionError("untrusted receipt cannot authorize actions")
    state = ("REVIEW_HOLD" if
             review.status == "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED"
             else "QUARANTINED")
    written = None
    if record_locally:
        # Append-only isolated review, never the ACTIVE catalog.
        written = journal.record(review, state=state)
    reason = ("INDEPENDENT_EXTERNAL_ORACLE_UNAVAILABLE",)
    return CandidateReceiptIntake(
        "LOCAL_SYNTHETIC_REVIEW_JOURNALLED_NOT_VERIFIED" if written else
        "HOLD_RECORD_REQUIRES_EXPLICIT_OPT_IN",
        candidate.candidate_sha256, review.review_sha256,
        written.entry_sha256 if written else None,
        tuple(sorted(set(review.reason_codes) | set(reason))))


# EAI-SWU-020: detached signing can prove possession of a pinned verifier key,
# but never prove the verifier's independence, the test's truth or owner GO.
@dataclass(frozen=True)
class DetachedCandidateSignatureReview:
    status: str
    candidate_sha256: str
    evidence_review_sha256: str
    verifier_id: str
    signature_sha256: str
    signer_key_sha256: str
    independently_verified_real_world: bool = False
    trusted_for_training: bool = False
    permits_active_promotion: bool = False
    grants_real_player_execution: bool = False


def verify_detached_candidate_signature(
    review: CandidateEvidenceReview, envelope: bytes, signature: bytes,
    *, pinned_public_key: bytes, trusted_public_key_sha256: str,
) -> DetachedCandidateSignatureReview:
    """Fail-closed ED25519 verification against a separately pinned key.

    Caller-selected or self-signed keys are not a configured trust authority.
    A valid signature only binds bounded, canonical, local review metadata.
    Proof of reviewer independence and semantic correctness remains external.
    """
    import re
    from .contracts import strict_json
    from hashlib import sha256
    from .contracts import canonical_bytes
    digest = re.compile(r"[0-9a-f]{64}\Z")
    identifier = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
    if (type(review) is not CandidateEvidenceReview
            or type(envelope) is not bytes or not 1 <= len(envelope) <= 2048
            or type(signature) is not bytes or len(signature) != 64
            or type(pinned_public_key) is not bytes
            or len(pinned_public_key) != 32
            or type(trusted_public_key_sha256) is not str
            or not digest.fullmatch(trusted_public_key_sha256)
            or sha256(pinned_public_key).hexdigest() != trusted_public_key_sha256):
        raise ValueError("independent externally pinned verifier input required")
    raw = strict_json(envelope, max_bytes=2048)
    if (type(raw) is not dict or set(raw) != {
            "schema", "candidate_sha256", "review_sha256",
            "fixture_sha256", "problem_sha256", "verifier_id",
            "disposition", "nonce"}
            or raw["schema"] != "eai.candidate.detached.review.v1"
            or raw["candidate_sha256"] != review.candidate_sha256
            or raw["review_sha256"] != review.review_sha256
            or raw["fixture_sha256"] != review.fixture_sha256
            or raw["problem_sha256"] != review.problem_sha256
            or raw["disposition"] != "REVIEW_METADATA_ONLY"
            or type(raw["verifier_id"]) is not str
            or not identifier.fullmatch(raw["verifier_id"])
            or type(raw["nonce"]) is not str
            or not re.fullmatch(r"[a-zA-Z0-9_-]{16,64}", raw["nonce"])
            or canonical_bytes(raw) != envelope):
        raise ValueError("detached review must bind canonical exact evidence")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey)
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        return DetachedCandidateSignatureReview(
            "HOLD_CRYPTOGRAPHIC_VERIFIER_NOT_INSTALLED",
            review.candidate_sha256, review.review_sha256,
            raw["verifier_id"], sha256(signature).hexdigest(),
            trusted_public_key_sha256)
    try:
        Ed25519PublicKey.from_public_bytes(pinned_public_key).verify(
            signature, envelope)
    except (InvalidSignature, ValueError):
        return DetachedCandidateSignatureReview(
            "HOLD_INVALID_DETACHED_SIGNATURE",
            review.candidate_sha256, review.review_sha256,
            raw["verifier_id"], sha256(signature).hexdigest(),
            trusted_public_key_sha256)
    return DetachedCandidateSignatureReview(
        "DETACHED_SIGNATURE_MATCHES_PIN_UNVERIFIED_INDEPENDENCE",
        review.candidate_sha256, review.review_sha256,
        raw["verifier_id"], sha256(signature).hexdigest(),
        trusted_public_key_sha256)
