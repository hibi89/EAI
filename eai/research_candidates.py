"""C32 non-authoritative candidate idea quarantine for local fake research.

OFF and unavailable mock outcome produce zero ideas. Accepted mock proposals
are metadata only: no arbitrary code, real actions, AXNODE import, training or
promotion. A future live adapter cannot reuse this function as authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .contracts import canonical_bytes
from .hydrogen_packet import ResearchPacket
from .research_mock_transport import MockOutcome, MockProposal

_ALLOWED_LOCAL_IDEAS = frozenset({"synthetic.counterexample.v1"})
_MOCK_SOURCE = "LOCAL_SYNTHETIC_FIXTURE"


@dataclass(frozen=True)
class QuarantinedResearchIdea:
    idea_sha256: str
    request_sha256: str
    idea_id: str
    task_family: str
    provenance: str = "LOCAL_FAKE_UNVERIFIED"
    can_execute: bool = False
    can_train: bool = False
    can_promote: bool = False


@dataclass(frozen=True)
class CandidateQuarantineReview:
    disposition: str
    request_sha256: str
    ideas: tuple[QuarantinedResearchIdea, ...]
    reason_codes: tuple[str, ...]
    permits_execution: bool = False
    permits_learning: bool = False
    permits_promotion: bool = False


def quarantine_mock_research(
    packet: ResearchPacket, outcome: MockOutcome,
) -> CandidateQuarantineReview:
    if type(packet) is not ResearchPacket or type(outcome) is not MockOutcome:
        raise ValueError("explicit typed local research payload required")
    # Direct construction of ResearchPacket is not a trust proof.
    checked = ResearchPacket.from_json(packet.to_json_bytes())
    digest = checked.request_sha256()
    reasons = []
    if outcome.request_sha256 != digest:
        reasons.append("CROSS_PACKET_MOCK_OUTPUT")
    if outcome.status != "MOCK_UNVERIFIED_ONLY":
        reasons.append("NO_ELIGIBLE_LOCAL_FAKE_OUTPUT")
    if type(outcome.candidates) is not tuple or len(outcome.candidates) != 1:
        return CandidateQuarantineReview(
            "HOLD_UNTRUSTED_FAKE_RESEARCH", digest, (),
            ("UNTRUSTED_CANDIDATE_COUNT",))
    if outcome.status == "MOCK_UNVERIFIED_ONLY" and (
            type(outcome.approval_sha256) is not str
            or len(outcome.approval_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in outcome.approval_sha256)
            or type(outcome.quota_index) is not int
            or outcome.quota_index < 1):
        reasons.append("MISSING_MOCK_PROVENANCE")
    for proposal in outcome.candidates[:2]:
        if (type(proposal) is not MockProposal
                or proposal.source != _MOCK_SOURCE
                or proposal.trust != "LOCAL_FAKE_UNVERIFIED"
                or type(proposal.idea_id) is not str
                or proposal.idea_id not in _ALLOWED_LOCAL_IDEAS
                or type(proposal.task_family) is not str
                or proposal.task_family != checked.task_family):
            reasons.append("UNTRUSTED_MODEL_CANDIDATE")
    if reasons:
        return CandidateQuarantineReview(
            "HOLD_UNTRUSTED_FAKE_RESEARCH", digest, (),
            tuple(sorted(set(reasons))))
    proposal = outcome.candidates[0]
    idea_sha = hashlib.sha256(canonical_bytes({
        "schema": "eai.local.fake.idea.v1",
        "request_sha256": digest,
        "idea_id": proposal.idea_id,
        "task_family": proposal.task_family,
        "source": _MOCK_SOURCE,
        "provenance": "LOCAL_FAKE_UNVERIFIED",
    })).hexdigest()
    return CandidateQuarantineReview(
        "QUARANTINED_LOCAL_FAKE_IDEA_ONLY", digest,
        (QuarantinedResearchIdea(
            idea_sha, digest, proposal.idea_id, proposal.task_family),), ())


# EAI-SWU-037: quarantine -> explicit EAI-owned manual research candidate view.
@dataclass(frozen=True)
class ArchitectResearchCandidate:
    status: str
    request_sha256: str
    idea_sha256: str | None
    strategy_id: str | None
    obligations: tuple[str, ...]
    reason_codes: tuple[str, ...]
    independent_verifier_passed: bool = False
    permitted_to_import: bool = False
    permitted_to_train: bool = False
    permitted_to_execute: bool = False
    permitted_to_promote: bool = False


def review_mock_idea_for_architect(
    packet: ResearchPacket, outcome: MockOutcome,
) -> ArchitectResearchCandidate:
    """Use existing strict local quarantine, then expose only review metadata."""
    quarantine = quarantine_mock_research(packet, outcome)
    if quarantine.disposition != "QUARANTINED_LOCAL_FAKE_IDEA_ONLY":
        return ArchitectResearchCandidate(
            "HOLD_UNTRUSTED_RESEARCH", quarantine.request_sha256,
            None, None, (), quarantine.reason_codes)
    if (len(quarantine.ideas) != 1 or
            quarantine.permits_execution or quarantine.permits_learning or
            quarantine.permits_promotion):
        raise ValueError("untrusted mock quarantine authority")
    idea = quarantine.ideas[0]
    if (type(idea) is not QuarantinedResearchIdea or idea.can_execute or
            idea.can_train or idea.can_promote or
            idea.request_sha256 != quarantine.request_sha256 or
            idea.provenance != "LOCAL_FAKE_UNVERIFIED" or
            idea.idea_id not in _ALLOWED_LOCAL_IDEAS):
        raise ValueError("forged quarantined research candidate")
    return ArchitectResearchCandidate(
        "LOCAL_MOCK_IDEA_REVIEW_ONLY", quarantine.request_sha256,
        idea.idea_sha256, idea.idea_id,
        ("INDEPENDENT_COUNTEREXAMPLE_ORACLE",
         "HOLDOUT_NON_REGRESSION",
         "HUMAN_REVIEW_BEFORE_ANY_PROMOTION"), ())
