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


# EAI-SWU-021: one-way quarantine intent, no ACTIVE or store status mutation.
@dataclass(frozen=True)
class QuarantineActivationIntent:
    status: str
    candidate_sha256: str
    node_sha256: str
    current_review_state: str
    affected_descendants: tuple[str, ...]
    reason_codes: tuple[str, ...]
    needs_owner_go: bool = True
    active_commit_performed: bool = False
    original_modified: bool = False
    may_activate: bool = False
    may_execute: bool = False


def review_quarantine_without_activation(
    store, journal: CandidateReviewJournal, review: CandidateEvidenceReview,
    node_sha256: str, *, current_active_sha256: str | None = None,
) -> QuarantineActivationIntent:
    """Graph impact and journal preflight only; no quarantine side effects."""
    from .axnode_store import AXNodeStore
    from .axnode_maintenance import plan_parent_invalidation
    if (type(store) is not AXNodeStore or
            type(journal) is not CandidateReviewJournal or
            type(review) is not CandidateEvidenceReview or
            type(node_sha256) is not str):
        raise ValueError("explicit typed AXNODE review inputs required")
    node = store.get(node_sha256)
    if node.sha256 != node_sha256:
        raise ValueError("stale node source")
    if (current_active_sha256 is not None and
            type(current_active_sha256) is not str):
        raise ValueError("untrusted active pointer")
    pre = inspect_activation_preflight(
        journal, review, current_active_sha256=current_active_sha256)
    impact = plan_parent_invalidation(store, node_sha256)
    reasons = set(pre.reasons)
    if pre.disposition != "ACTIVATION_FORBIDDEN" or pre.may_activate:
        raise ValueError("unsafe activation preflight result")
    if node.as_dict()["status"] == "ACTIVE":
        reasons.add("ACTIVE_NODE_REQUIRES_SEPARATE_OWNER_REVIEW")
    reasons.add("NODE_CANDIDATE_BINDING_NOT_INDEPENDENTLY_PROVEN")
    return QuarantineActivationIntent(
        "QUARANTINE_REVIEW_ONLY_NOT_APPLIED",
        review.candidate_sha256, node_sha256,
        pre.current_review_state, impact.affected_sha256,
        tuple(sorted(reasons)))
