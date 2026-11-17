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


# SWU-024: truly cumulative but NON-AUTHORIZING, bounded CPU research learner.
@dataclass(frozen=True)
class BoundedResearchPrior:
    problem_sha256: str
    candidate_sha256: tuple[str, ...]
    curriculum_sha256: tuple[str, ...]
    observed_synthetic_families: int
    # Each row is (candidate SHA, number of independently replayed research
    # batches, summed declared upper seconds, summed declared steps).
    aggregates: tuple[tuple[str, int, int, int], ...]
    status: str = "SYNTHETIC_CPU_RESEARCH_PRIOR_ONLY"
    independent_real_world_truth: bool = False
    trusted_training_permitted: bool = False
    active_promotion_permitted: bool = False


@dataclass(frozen=True)
class BoundedResearchUpdate:
    status: str
    prior: BoundedResearchPrior
    cost_ranked_candidate_sha256: tuple[str, ...]
    accepted: bool
    reason_codes: tuple[str, ...]
    real_world_uplift_verified: bool = False
    model_can_execute: bool = False


def advance_bounded_research_prior(
    store, problem, candidates, curriculum, prior: BoundedResearchPrior | None = None
) -> BoundedResearchUpdate:
    """Re-execute B0/B1 on a fresh disjoint synthetic curriculum before update.

    A failed attempt does NOT mutate old research state; the returned prior is
    the exact previous state. This is a research-only online cost preference:
    it does not fit accuracy, mint rewards, or certify an external outcome.
    """
    from .axnode_store import AXNodeStore
    from .contracts import ProblemSpec
    from .logic_synthesis import SynthesisCandidate
    from .strategy_research_ranker import rank_synthetic_strategy_previews
    from .synthetic_curriculum import SyntheticCurriculum
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec
            or type(candidates) is not tuple
            or not 1 <= len(candidates) <= 4
            or any(type(v) is not SynthesisCandidate for v in candidates)
            or type(curriculum) is not SyntheticCurriculum
            or (prior is not None and type(prior) is not BoundedResearchPrior)):
        raise ValueError("typed local synthetic CPU candidate/observation required")
    ids = tuple(sorted(c.candidate_sha256 for c in candidates))
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate research candidate hash")
    digest = problem.digest()
    if prior is None:
        prior = BoundedResearchPrior(
            digest, ids, (), 0, tuple((x, 0, 0, 0) for x in ids))
    if (prior.problem_sha256 != digest or prior.candidate_sha256 != ids
            or prior.status != "SYNTHETIC_CPU_RESEARCH_PRIOR_ONLY"
            or prior.independent_real_world_truth
            or prior.trusted_training_permitted
            or prior.active_promotion_permitted
            or type(prior.curriculum_sha256) is not tuple
            or len(prior.curriculum_sha256) > 8
            or len(set(prior.curriculum_sha256)) != len(prior.curriculum_sha256)
            or any(type(x) is not str or not _HASH.fullmatch(x)
                   for x in prior.curriculum_sha256)
            or type(prior.aggregates) is not tuple
            or len(prior.aggregates) != len(ids)
            or type(prior.observed_synthetic_families) is not int
            or prior.observed_synthetic_families != 4 * len(prior.curriculum_sha256)):
        raise ValueError("untrusted research-only prior")
    rows = dict()
    for entry in prior.aggregates:
        if (type(entry) is not tuple or len(entry) != 4
                or type(entry[0]) is not str or entry[0] in rows
                or entry[0] not in ids
                or any(type(n) is not int or n < 0 for n in entry[1:])
                or entry[1] != len(prior.curriculum_sha256)
                or entry[2] > entry[1] * 300
                or entry[3] > entry[1] * 64):
            raise ValueError("unsafe research state aggregate")
        rows[entry[0]] = entry[1:]
    if set(rows) != set(ids):
        raise ValueError("incomplete research prior")
    def ordered(p):
        # Stored tuple order is untrusted: always key by candidate SHA.
        values = {row[0]: row for row in p.aggregates}
        return tuple(sorted(ids, key=lambda x: (
            (values[x][2] * 1000 // max(1, values[x][1])) +
            (values[x][3] * 2000 // max(1, values[x][1])),
            x)))
    if (curriculum.manifest_sha256 in prior.curriculum_sha256 or
            len(prior.curriculum_sha256) >= 8):
        return BoundedResearchUpdate(
            "HOLD_REPLAYED_OR_EXHAUSTED_SYNTHETIC_FAMILY",
            prior, ordered(prior), False, ("FAMILY_ALREADY_USED_OR_LIMIT",))
    # Recompute B0/B1, including disjoint train/heldout checks. The newly
    # ranked prior cannot grant trust because the oracle is synthetic only.
    checked = rank_synthetic_strategy_previews(
        store, problem, candidates, curriculum)
    seen = {row.candidate_sha256: row for row in checked.ranked}
    if (len(seen) != len(ids) or set(seen) != set(ids)
            or checked.held or
            checked.curriculum_sha256 != curriculum.manifest_sha256
            or any(score.trusted_for_learning for score in checked.ranked)):
        return BoundedResearchUpdate(
            "HOLD_FAILED_SYNTHETIC_NO_REGRESSION_RETAIN_PREVIOUS",
            prior, ordered(prior), False,
            ("INDEPENDENT_SYNTHETIC_RECHECK_DID_NOT_COVER_EVERY_CANDIDATE",))
    next_rows = tuple((
        x, rows[x][0] + 1,
        rows[x][1] + seen[x].declared_seconds,
        rows[x][2] + seen[x].declared_steps,
    ) for x in ids)
    updated = BoundedResearchPrior(
        digest, ids, prior.curriculum_sha256+(curriculum.manifest_sha256,),
        prior.observed_synthetic_families + (
            len(curriculum.train)+len(curriculum.heldout)),
        next_rows)
    return BoundedResearchUpdate(
        "UPDATED_SYNTHETIC_CPU_PRIOR_UNVERIFIED",
        updated, ordered(updated), True, ())
