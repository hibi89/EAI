"""C15 explicit fail-closed ACTIVE preflight; no side-effectful promotion.

Even a perfectly consistent *synthetic* review chain is not sufficient for
activation. A separate approved verifier, owner scope and rollback mechanism
are required, none can be manufactured from model or AXNODE text.
"""
from __future__ import annotations

from dataclasses import dataclass

from .candidate_evidence_review import CandidateEvidenceReview
from .candidate_review_journal import CandidateReviewJournal


@dataclass(frozen=True)
class CandidateActivationPreflight:
    disposition: str
    candidate_sha256: str
    current_review_state: str
    prior_active_sha256: str | None
    reasons: tuple[str, ...]
    may_activate: bool = False
    may_modify_original: bool = False


def inspect_activation_preflight(
    journal: CandidateReviewJournal,
    review: CandidateEvidenceReview,
    *,
    current_active_sha256: str | None = None,
) -> CandidateActivationPreflight:
    if (type(journal) is not CandidateReviewJournal
            or type(review) is not CandidateEvidenceReview):
        raise ValueError("typed local review journal and candidate required")
    latest = journal.latest_for(review.candidate_sha256)
    state = latest.state if latest is not None else "NOT_REVIEWED"
    reasons = []
    if latest is None:
        reasons.append("NO_JOURNALLED_CANDIDATE_REVIEW")
    else:
        if latest.evidence_sha256 != review.review_sha256:
            reasons.append("REVIEW_EVIDENCE_SHA_CHANGED")
        if latest.previous_active_sha256 != current_active_sha256:
            reasons.append("ACTIVE_POINTER_CHANGED")
    if (review.status != "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED"
            or review.reason_codes or review.counterexample_families
            or review.permits_promotion or review.permits_learning
            or review.permits_real_execution):
        reasons.append("UNTRUSTED_SYNTHETIC_REVIEW")
    if state != "REVIEW_HOLD":
        reasons.append("NOT_IN_REVIEW_HOLD")
    # No mutable production/ACTIVE operations are implemented. The missing
    # trusted verifier/owner approval/rollback are never inferred from SHA.
    reasons.extend(("TRUSTED_INDEPENDENT_PROOF_MISSING",
                    "OWNER_EXACT_SCOPE_APPROVAL_MISSING",
                    "REVERSIBLE_ACTIVE_COMMIT_NOT_IMPLEMENTED"))
    return CandidateActivationPreflight(
        "ACTIVATION_FORBIDDEN", review.candidate_sha256,
        state, current_active_sha256, tuple(sorted(set(reasons))))
