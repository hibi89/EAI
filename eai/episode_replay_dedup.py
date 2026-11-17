"""C16 read-only, cross-batch episode fingerprint and negative-memory screen.

No learner inputs are admitted. A caller's previous fingerprint set is
untrusted context; absence of it does not assert durable replay protection.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .candidate_evidence_review import CandidateEvidenceReview
from .contracts import ProblemSpec, canonical_bytes
from .episode_replay import EpisodeReplayDecision
from .logic_synthesis import SynthesisCandidate

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_IDS = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")


@dataclass(frozen=True)
class EpisodeBatchReview:
    status: str
    candidate_sha256: str
    reviewed_fingerprints: tuple[str, ...]
    rejected_memory_hashes: tuple[str, ...]
    reasons: tuple[str, ...]
    admits_training: bool = False
    grants_execution: bool = False


def screen_episodes_for_manual_review(
    problem: ProblemSpec, candidate: SynthesisCandidate,
    episodes: tuple[EpisodeReplayDecision, ...],
    evidence: CandidateEvidenceReview,
    *, prior_fingerprints: tuple[str, ...] = (),
) -> EpisodeBatchReview:
    if (type(problem) is not ProblemSpec
            or type(candidate) is not SynthesisCandidate
            or type(evidence) is not CandidateEvidenceReview
            or type(episodes) is not tuple or not 1 <= len(episodes) <= 32
            or type(prior_fingerprints) is not tuple
            or len(prior_fingerprints) > 2048):
        raise ValueError("bounded typed episode batch required")
    if (any(type(p) is not str or not _HASH.fullmatch(p)
            for p in prior_fingerprints)
            or len(set(prior_fingerprints)) != len(prior_fingerprints)):
        raise ValueError("untrusted prior episode fingerprint inventory")
    reasons, accepted, rejected = set(), [], []
    if (evidence.candidate_sha256 != candidate.candidate_sha256
            or evidence.problem_sha256 != problem.digest()
            or evidence.status != "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED"
            or evidence.reason_codes or evidence.counterexample_families
            or evidence.permits_learning or evidence.permits_promotion
            or evidence.permits_real_execution):
        reasons.add("UNTRUSTED_OR_UNRELATED_SYNTHETIC_REVIEW")
    seen_refs, seen_fingerprints = set(), set(prior_fingerprints)
    for episode in episodes:
        if type(episode) is not EpisodeReplayDecision:
            raise ValueError("typed episode required")
        if (type(episode.memory_sha256) is not str
                or not _HASH.fullmatch(episode.memory_sha256)
                or type(episode.source_node_sha256) is not str
                or not _HASH.fullmatch(episode.source_node_sha256)
                or type(episode.label) is not str
                or not _IDS.fullmatch(episode.label)):
            raise ValueError("invalid episode reference")
        fingerprint = hashlib.sha256(canonical_bytes({
            "schema": "eai.episode.replay.reference.v1",
            "problem_sha256": problem.digest(),
            "candidate_sha256": candidate.candidate_sha256,
            "memory_sha256": episode.memory_sha256,
            "source_node_sha256": episode.source_node_sha256,
            "label": episode.label,
        })).hexdigest()
        negative = (
            episode.source_node_sha256 not in candidate.node_hashes
            or episode.evidence_state != "SUPPORTED_UNVERIFIED"
            or episode.disposition != "REPLAYED_UNVERIFIED_FOR_MANUAL_REVIEW"
            or episode.independent_verification != "NOT_ESTABLISHED"
            or episode.automated_execution_allowed
            or episode.automated_learning_allowed
        )
        repeated = (episode.memory_sha256 in seen_refs
                    or fingerprint in seen_fingerprints)
        seen_refs.add(episode.memory_sha256)
        seen_fingerprints.add(fingerprint)
        if repeated:
            reasons.add("DUPLICATE_OR_REPLAYED_EPISODE")
        if negative:
            reasons.add("NEGATIVE_OR_UNSUPPORTED_EPISODE")
        if repeated or negative:
            rejected.append(episode.memory_sha256)
        else:
            accepted.append(fingerprint)
    # Never expose an accepted subset of a rejected batch: downstream
    # callers must not accidentally reward the first of two duplicates.
    if reasons:
        accepted.clear()
    status = ("SYNTHETIC_EPISODE_MANUAL_REVIEW_ONLY" if not reasons
              else "HOLD_UNTRUSTED_OR_REPLAYED_EPISODES")
    return EpisodeBatchReview(
        status, candidate.candidate_sha256, tuple(sorted(accepted)),
        tuple(sorted(set(rejected))), tuple(sorted(reasons)))
