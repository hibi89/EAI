"""EAI-SWU-024 bounded local CPU research updates, NOT trusted learning.

All outcomes remain synthetic/unverified and in-memory only. The real
verified-outcome learner is unavailable until an independent source verifier
and owner-governed admission are supplied; this module cannot fake them.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ResearchStrategyObservation:
    candidate_sha256: str
    synthetic_cost_steps: int
    synthetic_cost_seconds: int
    family: str
    verified_real_world: bool = False


@dataclass(frozen=True)
class ResearchStrategyUpdate:
    candidate_sha256: str
    observations: int
    mean_declared_seconds: int
    mean_declared_steps: int
    disposition: str
    can_train_trusted_model: bool = False
    may_promote: bool = False
    may_execute: bool = False
    accuracy_established: bool = False


def derive_synthetic_strategy_prior(
    candidate_sha256: str, observations: tuple[ResearchStrategyObservation, ...],
    *, update_research_prior: bool = False,
) -> ResearchStrategyUpdate:
    """Bounded CPU numerical update; never persist or use as trusted reward."""
    if (type(candidate_sha256) is not str or
            not _HASH.fullmatch(candidate_sha256)
            or type(observations) is not tuple or
            not 1 <= len(observations) <= 32
            or type(update_research_prior) is not bool):
        raise ValueError("typed bounded research-only observations required")
    seen = set()
    total_seconds = total_steps = 0
    for item in observations:
        if (type(item) is not ResearchStrategyObservation
                or item.candidate_sha256 != candidate_sha256
                or item.verified_real_world is not False
                or type(item.family) is not str
                or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", item.family)
                or item.family in seen
                or type(item.synthetic_cost_steps) is not int
                or not 1 <= item.synthetic_cost_steps <= 64
                or type(item.synthetic_cost_seconds) is not int
                or not 1 <= item.synthetic_cost_seconds <= 300):
            raise ValueError("untrusted or duplicate synthetic strategy input")
        seen.add(item.family)
        total_steps += item.synthetic_cost_steps
        total_seconds += item.synthetic_cost_seconds
    return ResearchStrategyUpdate(
        candidate_sha256, len(observations),
        (total_seconds + len(observations) - 1) // len(observations),
        (total_steps + len(observations) - 1) // len(observations),
        "SYNTHETIC_RESEARCH_PRIOR_UNVERIFIED" if update_research_prior
        else "HOLD_EXPLICIT_RESEARCH_UPDATE_REQUIRED")
