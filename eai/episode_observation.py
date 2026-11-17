"""EAI-SWU-022 pure Player local observation -> five-tier memory ledger.

Only a deterministic synthetic no-op trace can supply an episode here.
No real tool outcome, learner admission, evidence verification or promotion.
"""
from __future__ import annotations

from dataclasses import dataclass

from .axnode_memory import AXNodeMemory
from .contracts import PlanSpec, ProblemSpec
from .evidence_ledger import EvidenceLedger
from .episode_replay import record_and_review_experience
from .player_runtime import PurePlayerPreview, audit_pure_player_trace
from .policy_gate import PlanPolicyDecision


@dataclass(frozen=True)
class LocalEpisodeObservation:
    status: str
    trace_sha256: str
    memory_sha256: str | None
    source_node_sha256: str
    observed_outcome: str
    memory_disposition: str
    independent_verification: str = "NOT_ESTABLISHED"
    can_train: bool = False
    can_execute: bool = False
    can_promote: bool = False


def observe_and_record_pure_episode(
    memory: AXNodeMemory, evidence: EvidenceLedger | None,
    problem: ProblemSpec, plan: PlanSpec, policy: PlanPolicyDecision,
    receipt: PurePlayerPreview, *, source_node_sha256: str,
    observed_outcome: str = "UNKNOWN",
    cancel_before_step: str | None = None,
    record_local: bool = False,
    observed_at: int | None = None,
) -> LocalEpisodeObservation:
    """Verify pure replay first; explicitly record only unverified observation.

    "SUCCESS_OBSERVED" and "FAILURE_OBSERVED" remain untrusted local metadata
    and never become a proof that real-world actions succeeded or failed.
    """
    if (type(memory) is not AXNodeMemory or
            type(problem) is not ProblemSpec or
            type(plan) is not PlanSpec or
            type(policy) is not PlanPolicyDecision or
            type(receipt) is not PurePlayerPreview or
            type(record_local) is not bool or
            type(observed_outcome) is not str or
            observed_outcome not in {
                "UNKNOWN", "SUCCESS_OBSERVED", "FAILURE_OBSERVED"}):
        raise ValueError("typed pure local episode and explicit switch required")
    if evidence is not None and (
            type(evidence) is not EvidenceLedger
            or evidence.store is not memory.store):
        raise ValueError("cross-store evidence not allowed")
    node = memory.store.get(source_node_sha256)
    if node.sha256 != source_node_sha256:
        raise ValueError("stale episode AXNODE source")
    audit = audit_pure_player_trace(
        problem, plan, policy, receipt,
        cancel_before_step=cancel_before_step)
    if audit.status != "PURE_TRACE_REPLAY_MATCH_UNVERIFIED":
        raise ValueError("unreproducible pure episode receipt")
    if receipt.external_actions or receipt.original_writes or (
            receipt.real_world_verified or receipt.promotion_authorized):
        raise PermissionError("real-world or promoted Player result forbidden")
    if (receipt.status == "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED"
            and observed_outcome == "SUCCESS_OBSERVED"):
        raise ValueError("cancelled Player cannot claim observed success")
    if not record_local:
        return LocalEpisodeObservation(
            "HOLD_EXPLICIT_EPISODE_RECORD_REQUIRED", receipt.trace_sha256,
            None, source_node_sha256, observed_outcome, "NOT_RECORDED")
    tier = ("NEGATIVE" if observed_outcome == "FAILURE_OBSERVED"
            else "EPISODIC")
    tags = ("pure.noop", "trace." + receipt.trace_sha256[:32])
    reviewed = record_and_review_experience(
        memory, evidence, tier=tier, anchor_sha=source_node_sha256,
        label=node.as_dict()["id"], tags=tags,
        outcome=observed_outcome, captured_at=observed_at)
    return LocalEpisodeObservation(
        "RECORDED_LOCAL_UNVERIFIED", receipt.trace_sha256,
        reviewed.memory_sha256, source_node_sha256,
        observed_outcome, reviewed.disposition)
