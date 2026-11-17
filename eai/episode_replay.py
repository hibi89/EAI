"""Fail-closed read-only replay of recorded AXNODE memory and claim observations.

Observing a result is not independent verification. Replay never trains,
promotes, executes, deletes or rewrites data; it only supplies review labels.
"""
from __future__ import annotations

from dataclasses import dataclass

from .axnode_memory import AXNodeMemory
from .axnode_memory_review import review_memory_reuse
from .evidence_ledger import EvidenceLedger


@dataclass(frozen=True)
class EpisodeReplayDecision:
    label: str
    memory_sha256: str
    source_node_sha256: str
    observation_tier: str
    evidence_state: str
    disposition: str
    independent_verification: str = "NOT_ESTABLISHED"
    automated_learning_allowed: bool = False
    automated_execution_allowed: bool = False


def replay_memory_evidence(
        memory: AXNodeMemory, evidence: EvidenceLedger | None,
        query: str, *, withdrawn_hashes: tuple[str, ...] = (),
        now: int | None = None, limit: int = 12
        ) -> tuple[EpisodeReplayDecision, ...]:
    if type(memory) is not AXNodeMemory:
        raise ValueError("explicit AXNODE memory index required")
    if evidence is not None and type(evidence) is not EvidenceLedger:
        raise ValueError("explicit untrusted EvidenceLedger or None required")
    if evidence is not None and (
            evidence.store is not memory.store or
            evidence.path.parent.resolve(strict=True) !=
            memory.store.root.resolve(strict=True)):
        raise ValueError("cross-store evidence must not be trusted")
    reviewed = review_memory_reuse(
        memory, query, withdrawn_hashes=withdrawn_hashes,
        now=now, limit=limit)
    decisions = []
    for review in reviewed:
        state = "NO_EVIDENCE_LEDGER"
        if evidence is not None:
            assessment = evidence.assess(review.label, now=now)
            state = assessment.state
        if review.disposition != "UNVERIFIED_CANDIDATE_ONLY":
            result = review.disposition
        elif state in ("CONTRADICTED_UNVERIFIED", "REFUTED_UNVERIFIED"):
            result = "HOLD_CONTRADICTED_EVIDENCE"
        elif state == "STALE_UNVERIFIED":
            result = "HOLD_STALE_EVIDENCE"
        elif state == "SUPPORTED_UNVERIFIED":
            result = "REPLAYED_UNVERIFIED_FOR_MANUAL_REVIEW"
        else:
            result = "HOLD_NO_INDEPENDENT_EVIDENCE"
        decisions.append(EpisodeReplayDecision(
            label=review.label, memory_sha256=review.memory_sha256,
            source_node_sha256=review.anchor_sha256,
            observation_tier=review.tier, evidence_state=state,
            disposition=result))
    return tuple(decisions)


# EAI-SWU-010: actual local observation write -> five-tier replay -> decision.
@dataclass(frozen=True)
class ExperienceMemoryDecision:
    memory_sha256: str
    source_node_sha256: str
    tier: str
    outcome: str
    disposition: str
    evidence_state: str
    five_tier_model: tuple[str, ...] = (
        "WORKING", "EPISODIC", "SEMANTIC", "PROCEDURAL", "NEGATIVE")
    independently_verified: bool = False
    can_train: bool = False
    can_execute: bool = False
    can_promote: bool = False


def record_and_review_experience(
    memory: AXNodeMemory, evidence: EvidenceLedger | None, *,
    tier: str, anchor_sha: str, label: str,
    tags: tuple[str, ...] = (), outcome: str = "UNKNOWN",
    captured_at: int | None = None, ttl_seconds: int | None = None,
    withdrawn_hashes: tuple[str, ...] = (),
) -> ExperienceMemoryDecision:
    """Record only existing bounded local metadata, then re-evaluate it.

    A successful observation is NOT independent truth or learning permission.
    Failure/withdrawal/contradiction can only block reuse.
    """
    if type(memory) is not AXNodeMemory or (
            evidence is not None and (
                type(evidence) is not EvidenceLedger or
                evidence.store is not memory.store)):
        raise ValueError("same-store typed memory and evidence required")
    digest = memory.remember(
        tier=tier, anchor_sha=anchor_sha, label=label, tags=tags,
        outcome=outcome, captured_at=captured_at, ttl_seconds=ttl_seconds)
    stored = memory.get(digest)
    if (stored["tier"] != tier or stored["anchor_sha"] != anchor_sha or
            stored["label"] != label or stored["outcome"] != outcome):
        raise ValueError("new memory record did not round-trip")
    decisions = replay_memory_evidence(
        memory, evidence, label, withdrawn_hashes=withdrawn_hashes,
        now=captured_at, limit=25)
    matching = [d for d in decisions if d.memory_sha256 == digest]
    if len(matching) != 1:
        return ExperienceMemoryDecision(
            digest, anchor_sha, tier, outcome,
            "HOLD_MEMORY_NOT_REPLAYABLE", "NO_INDEPENDENT_EVIDENCE")
    reviewed = matching[0]
    return ExperienceMemoryDecision(
        digest, anchor_sha, tier, outcome,
        reviewed.disposition, reviewed.evidence_state)
