"""Strict C16/C17 boundary for synthetic experience candidates.

A successful legacy CPU baseline is NOT proof that a newly composed AXNODE
ran correctly. This gate creates only a hash-pinned *manual review queue*,
never a training signal, ACTIVE node, executable permission or verified fact.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .axnode_store import AXNodeStore
from .candidate_evidence_review import CandidateEvidenceReview
from .contracts import ProblemSpec, canonical_bytes
from .episode_replay import EpisodeReplayDecision
from .logic_synthesis import SynthesisCandidate
from .logic_verifier import StructuralVerifier
from .solver_reference_check import ActualSolverAudit

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")


@dataclass(frozen=True)
class ExperienceGateResult:
    disposition: str
    candidate_sha256: str
    review_fingerprint: str
    eligible_memory_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    eligible_for_learning: bool = False
    eligible_for_execution: bool = False
    candidate_semantically_verified: bool = False


def inspect_learning_admission(
        store: AXNodeStore, problem: ProblemSpec,
        candidate: SynthesisCandidate, baseline: ActualSolverAudit,
        episodes: tuple[EpisodeReplayDecision, ...], *,
        candidate_review: CandidateEvidenceReview | None = None
        ) -> ExperienceGateResult:
    """Pure read-only review: no positive learning admission until new gate."""
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec or
            type(candidate) is not SynthesisCandidate or
            type(baseline) is not ActualSolverAudit or
            type(episodes) is not tuple or len(episodes) > 32 or
            any(type(e) is not EpisodeReplayDecision for e in episodes)
            or (candidate_review is not None
                and type(candidate_review) is not CandidateEvidenceReview)):
        raise ValueError("bounded trusted-contract input required")
    if type(candidate.candidate_sha256) is not str or not _HASH.fullmatch(
            candidate.candidate_sha256):
        raise ValueError("invalid candidate fingerprint")
    structural = StructuralVerifier(store).check(problem, candidate)
    if structural.status != "STRUCTURE_ONLY_UNVERIFIED":
        reasons = ["CANDIDATE_STRUCTURE_NOT_REVERIFIED"]
    else:
        reasons = []
    if candidate_review is not None:
        # Synthetic cross-check remains advisory even when all hashes agree.
        # A forged/unrelated review may not launder an episode into the queue.
        if (candidate_review.candidate_sha256 != candidate.candidate_sha256
                or candidate_review.problem_sha256 != problem.digest()
                or candidate_review.status != "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED"
                or candidate_review.reason_codes or candidate_review.counterexample_families
                or candidate_review.permits_promotion
                or candidate_review.permits_learning
                or candidate_review.permits_real_execution
                or type(candidate_review.review_sha256) is not str
                or not _HASH.fullmatch(candidate_review.review_sha256)
                or type(candidate_review.fixture_sha256) is not str
                or not _HASH.fullmatch(candidate_review.fixture_sha256)):
            reasons.append("UNTRUSTED_OR_UNRELATED_CANDIDATE_REVIEW")
    if baseline.candidate_sha256 != candidate.candidate_sha256:
        reasons.append("BASELINE_CANDIDATE_SHA_MISMATCH")
    if (baseline.composed_candidate_executed or baseline.semantic_verified or
            baseline.permits_promotion or
            any(item.composed_candidate_executed for item in baseline.results)):
        reasons.append("UNTRUSTED_AUTHORITY_ASSERTED")
    if (baseline.disposition !=
            "CPU_BASELINE_MATCHES_CANDIDATE_STILL_UNVERIFIED" or
            not baseline.baseline_cpu_executed or len(baseline.results) < 2 or
            any(item.verdict != "BASELINE_CPU_MATCH_UNVERIFIED"
                or not item.baseline_executed for item in baseline.results)):
        reasons.append("INDEPENDENT_CPU_BASELINE_NOT_ESTABLISHED")
    if not episodes:
        reasons.append("NO_MEMORY_OBSERVATION")
    refs = []
    for item in episodes:
        if (type(item.memory_sha256) is not str or
                not _HASH.fullmatch(item.memory_sha256) or
                type(item.source_node_sha256) is not str or
                not _HASH.fullmatch(item.source_node_sha256) or
                type(item.label) is not str or not _ID.fullmatch(item.label)):
            raise ValueError("invalid opaque episode reference")
        if item.source_node_sha256 not in candidate.node_hashes:
            reasons.append("EPISODE_NODE_OUTSIDE_CANDIDATE")
        if (item.evidence_state != "SUPPORTED_UNVERIFIED" or
                item.disposition != "REPLAYED_UNVERIFIED_FOR_MANUAL_REVIEW"):
            reasons.append("NEGATIVE_STALE_OR_UNSUPPORTED_EPISODE")
        if (item.independent_verification != "NOT_ESTABLISHED" or
                item.automated_learning_allowed or
                item.automated_execution_allowed):
            reasons.append("FORGED_EPISODE_AUTHORITY")
        refs.append(item.memory_sha256)
    if len(refs) != len(set(refs)):
        reasons.append("DUPLICATE_EPISODE_PROVENANCE")
    if not reasons:
        # This is a manual review queue, not verified episodes or a learner.
        reasons.append("ACTUAL_COMPOSED_CANDIDATE_INDEPENDENT_ORACLE_MISSING")
        decision = "SYNTHETIC_REVIEW_ONLY_NOT_TRAINING"
        candidates = tuple(sorted(refs))
    else:
        decision = "HOLD_UNTRUSTED_OR_INCOMPLETE_EXPERIENCE"
        candidates = ()
    fingerprint = hashlib.sha256(canonical_bytes({
        "schema": "eai.experience.admission.review.v1",
        "candidate_sha256": candidate.candidate_sha256,
        "candidate_review_sha256": (
            candidate_review.review_sha256 if candidate_review else None),
        "review_memory_sha256": list(candidates),
        "decision": decision,
        "reasons": sorted(set(reasons)),
    })).hexdigest()
    return ExperienceGateResult(
        decision, candidate.candidate_sha256, fingerprint, candidates,
        tuple(sorted(set(reasons))))
