"""Bounded synthetic research and local verified-outcome strategy updates."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .experience_admission import VerifiedEpisodeBatch
from .logic_synthesis import SynthesisCandidate

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
    synthetic_scenario_families_checked: int = 0
    synthetic_scenario_candidate_matches: int = 0
    synthetic_scenario_regression_rejected: bool = False


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
    if any(type(c.candidate_sha256) is not str or
           not _HASH.fullmatch(c.candidate_sha256) for c in candidates):
        raise ValueError("untrusted research candidate fingerprint")
    ids = tuple(sorted(c.candidate_sha256 for c in candidates))
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate research candidate hash")
    digest = problem.digest()
    if prior is None:
        prior = BoundedResearchPrior(
            digest, ids, (), 0, tuple((x, 0, 0, 0) for x in ids))
    if (prior.problem_sha256 != digest or prior.candidate_sha256 != ids
            or prior.status != "SYNTHETIC_CPU_RESEARCH_PRIOR_ONLY"
            or prior.independent_real_world_truth is not False
            or prior.trusted_training_permitted is not False
            or prior.active_promotion_permitted is not False
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
    if checked.disposition != "SYNTHETIC_COST_ORDER_ONLY_NOT_LEARNING":
        return BoundedResearchUpdate(
            "HOLD_UNTRUSTED_SYNTHETIC_RESEARCH_RESULT",
            prior, ordered(prior), False, ("RECHECKED_COST_ORDER_NOT_ESTABLISHED",))
    # A seeded re-run of the same four fixture TYPES is not a transfer test.
    # Require different synthetic scenario classes and independently replay
    # their actual CPU B0 vs AXNODE interpreter B1 outputs before changing
    # cumulative research state. No promise of genuine general OOD accuracy.
    from .synthetic_scenario_transfer import (
        SyntheticScenarioTransfer, evaluate_synthetic_scenario_transfer,
    )
    challenged = []
    try:
        for candidate in candidates:
            probe = evaluate_synthetic_scenario_transfer(
                store, problem, candidate, curriculum)
            challenged.append(probe)
    except (ValueError, KeyError, TypeError):
        return BoundedResearchUpdate(
            "HOLD_SYNTHETIC_SCENARIO_RECHECK_RETAIN_PREVIOUS",
            prior, ordered(prior), False,
            ("SYNTHETIC_SCENARIO_RECHECK_FAILED",),
            synthetic_scenario_regression_rejected=True)
    # A PASS label alone is not evidence. Bind every rechecked report to its
    # exact candidate, expected scenario classes and bounded CPU comparisons.
    # This guards the research-state boundary even if a caller or test double
    # supplies a forged "successful" dataclass with inconsistent counters.
    if any(
            type(p) is not SyntheticScenarioTransfer
            or p.candidate_sha256 != candidate.candidate_sha256
            or p.status != "SYNTHETIC_SCENARIO_TRANSFER_MATCH_UNVERIFIED"
            or p.semantic_scope != "SYNTHETIC_SCENARIO_TRANSFER_NOT_GENERAL_OOD"
            or p.scenario_types != (
                "negative_signed_decimals", "multiple_key_and_value_changes")
            or type(p.challenge_families) is not int
            or p.challenge_families != 2
            or type(p.b0_checked) is not int or p.b0_checked != 2
            or type(p.b1_checked) is not int or p.b1_checked != 2
            or type(p.b1_unmatched) is not int or p.b1_unmatched != 0
            or p.permits_learning is not False
            or p.permits_promotion is not False
            or p.independently_verified_real_world is not False
            for candidate, p in zip(candidates, challenged)
    ):
        checked_count = sum(
            p.challenge_families for p in challenged
            if type(p) is SyntheticScenarioTransfer
            and type(p.challenge_families) is int
            and p.challenge_families == 2)
        matched_count = sum(
            p.b1_checked for p in challenged
            if type(p) is SyntheticScenarioTransfer
            and type(p.b1_checked) is int and 0 <= p.b1_checked <= 2)
        return BoundedResearchUpdate(
            "HOLD_SYNTHETIC_SCENARIO_REGRESSION_RETAIN_PREVIOUS",
            prior, ordered(prior), False,
            ("SYNTHETIC_SCENARIO_TRANSFER_COUNTEREXAMPLE",),
            synthetic_scenario_families_checked=checked_count,
            synthetic_scenario_candidate_matches=matched_count,
            synthetic_scenario_regression_rejected=True)
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
        updated, ordered(updated), True, (),
        synthetic_scenario_families_checked=sum(p.challenge_families for p in challenged),
        synthetic_scenario_candidate_matches=sum(p.b1_checked for p in challenged))


@dataclass(frozen=True)
class VerifiedHeldoutMeasure:
    """Bounded, signed-local-case comparison, NOT general OOD or production accuracy."""

    baseline_evaluated: int
    preferred_evaluated: int
    selected_evaluated: int | None
    baseline_errors: int
    preferred_errors: int
    selected_errors: int | None
    preferred_extra_errors: int
    selected_extra_errors: int | None
    selected_step_delta: int | None
    selected_declared_seconds_delta: int | None
    regression_rejected: bool
    selected_no_regression_on_pinned_cases: bool
    scope: str = "OWNER_SIGNED_LOCAL_HELDOUT_RECONCILIATION_ONLY"
    independent_general_ood: bool = False
    permits_active_promotion: bool = False
    production_accuracy_established: bool = False


@dataclass(frozen=True)
class VerifiedStrategyUpdate:
    """One local advisory selection and its owner-pinned held-out result."""

    status: str
    baseline_sha256: str
    training_preference_sha256: str
    advisory_candidate_sha256: str | None
    training_errors: tuple[tuple[str, int], ...]
    held_out_errors: tuple[tuple[str, int], ...]
    policy_sha256: str
    journal_entry_sha256: tuple[str, ...]
    valid_until: int
    fallback_candidate_sha256: str | None
    selection_sha256: str | None = None
    heldout_measure: VerifiedHeldoutMeasure | None = None


def _fit_verified_strategy(
    candidates: tuple[SynthesisCandidate, ...], batch: VerifiedEpisodeBatch,
) -> VerifiedStrategyUpdate:
    """Fit one ranking from training cases, then check the proposed selection."""
    inventory = {candidate.candidate_sha256: candidate for candidate in candidates}
    baseline = batch.baseline_sha256
    training_errors = dict.fromkeys(inventory, 0)
    # Quantify exact owner-signed train/held-out case coverage per candidate.
    # Reject missing or reclassified cases before any strategy selection.
    evaluated = {digest: {"TRAIN": 0, "HELD_OUT": 0} for digest in inventory}
    for episode in batch.episodes:
        if (episode.candidate_sha256 not in inventory or
                episode.partition not in ("TRAIN", "HELD_OUT")):
            raise ValueError("unknown verified episode candidate or split")
        evaluated[episode.candidate_sha256][episode.partition] += 1
        if episode.partition == "TRAIN" and not episode.correct:
            training_errors[episode.candidate_sha256] += 1
    if (any(min(counts.values()) < 2 for counts in evaluated.values())
            or len({(counts["TRAIN"], counts["HELD_OUT"])
                    for counts in evaluated.values()}) != 1):
        raise ValueError("missing signed training or held-out candidate coverage")
    champion = min(inventory, key=lambda digest: (
        training_errors[digest], inventory[digest].step_count,
        inventory[digest].predicted_seconds, digest != baseline, digest,
    ))
    # Evaluate only the proposed selection and the owner-pinned fallback.
    # A held-out failure cannot cause a search for a different challenger.
    held_out_errors = dict.fromkeys((baseline, champion), 0)
    for episode in batch.episodes:
        if (episode.partition == "HELD_OUT"
                and episode.candidate_sha256 in held_out_errors and not episode.correct):
            held_out_errors[episode.candidate_sha256] += 1

    preferred, previous = inventory[champion], inventory[baseline]
    fewer_operators = (preferred.step_count < previous.step_count
                       and preferred.predicted_seconds <= previous.predicted_seconds)
    safe_baseline = training_errors[baseline] == held_out_errors[baseline] == 0
    safe_champion = training_errors[champion] == held_out_errors[champion] == 0
    if (champion != baseline and safe_champion and (not safe_baseline or fewer_operators)):
        status, selected = "UPDATED_LOCAL_ADVISORY_STRATEGY", champion
    elif not safe_baseline:
        status, selected = "HOLD_NO_VERIFIED_FALLBACK", None
    elif champion != baseline and held_out_errors[champion] > 0:
        status, selected = "ROLLBACK_HELD_OUT_REGRESSION", baseline
    else:
        status, selected = "RETAIN_BASELINE_NO_HELD_OUT_UPLIFT", baseline

    baseline_count = evaluated[baseline]["HELD_OUT"]
    preferred_count = evaluated[champion]["HELD_OUT"]
    selected_count = evaluated[selected]["HELD_OUT"] if selected else None
    selected_errors = held_out_errors[selected] if selected else None
    baseline_errors = held_out_errors[baseline]
    preferred_errors = held_out_errors[champion]
    selected_delta = (
        selected_errors - baseline_errors if selected_errors is not None else None)
    # Counts compare only cases the owner signed, not distribution-wide OOD
    # performance. Cost deltas are declared limits, not timed measurements.
    measured = VerifiedHeldoutMeasure(
        baseline_count, preferred_count, selected_count,
        baseline_errors, preferred_errors, selected_errors,
        preferred_errors - baseline_errors, selected_delta,
        inventory[selected].step_count - inventory[baseline].step_count
        if selected else None,
        inventory[selected].predicted_seconds - inventory[baseline].predicted_seconds
        if selected else None,
        champion != baseline and preferred_errors > baseline_errors,
        selected_delta is not None and selected_delta <= 0)
    if selected_delta is not None and selected_delta > 0:
        raise PermissionError("held-out regression must never become selected")
    return VerifiedStrategyUpdate(
        status, baseline, champion, selected, tuple(sorted(training_errors.items())),
        tuple(sorted(held_out_errors.items())), batch.policy_sha256,
        batch.journal_entry_sha256, batch.valid_until,
        baseline if safe_baseline else None,
        heldout_measure=measured)
