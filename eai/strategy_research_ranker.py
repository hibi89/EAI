"""C17 synthetic cost research and verified local advisory strategy ranking."""
from __future__ import annotations

from dataclasses import dataclass, replace
from time import perf_counter_ns, process_time_ns

from .axnode_store import AXNodeStore
from .candidate_evidence_review import ReconciliationCase, SignedReconciliationReview
from .candidate_review_journal import CandidateReviewJournal
from .contracts import ProblemSpec
from .experience_admission import _admitting_verified_episodes
from .logic_synthesis import LogicSynthesizer, SynthesisCandidate
from .synthetic_candidate_benchmark import SyntheticB1Benchmark, benchmark_synthetic_candidate
from .synthetic_curriculum import SyntheticCurriculum, generate_synthetic_curriculum
from .strategy_learner import (
    BoundedResearchPrior, VerifiedStrategyUpdate, _fit_verified_strategy,
    advance_bounded_research_prior,
)


@dataclass(frozen=True)
class SyntheticStrategyScore:
    candidate_sha256: str
    review_status: str
    compared_train: int
    compared_heldout: int
    declared_steps: int
    declared_seconds: int
    trusted_for_learning: bool = False
    measured_synthetic_cpu_ms: int | None = None


@dataclass(frozen=True)
class StrategyRankingPreview:
    disposition: str
    problem_sha256: str
    curriculum_sha256: str
    ranked: tuple[SyntheticStrategyScore, ...]
    held: tuple[tuple[str, str], ...]
    learner_trained: bool = False
    verified_uplift: str = "NOT_MEASURED"
    permits_promotion: bool = False
    permits_real_execution: bool = False


def rank_synthetic_strategy_previews(
    store: AXNodeStore, problem: ProblemSpec,
    candidates: tuple[SynthesisCandidate, ...],
    curriculum: SyntheticCurriculum,
) -> StrategyRankingPreview:
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec
            or type(candidates) is not tuple or not 1 <= len(candidates) <= 4
            or type(curriculum) is not SyntheticCurriculum):
        raise ValueError("explicit bounded synthetic strategy inputs required")
    if curriculum != generate_synthetic_curriculum(curriculum.seed):
        raise ValueError("forged or cross-split synthetic curriculum")
    if (any(type(c) is not SynthesisCandidate for c in candidates)
            or len({c.candidate_sha256 for c in candidates}) != len(candidates)):
        raise ValueError("untrusted or repeated candidate inventory")
    scored, held = [], []
    for candidate in candidates:
        try:
            rebuilt = LogicSynthesizer(store).compose(
                problem, candidate.node_hashes)
            if rebuilt != candidate:
                held.append((candidate.candidate_sha256,
                             "CANDIDATE_STRUCTURE_OR_HASH_CHANGED"))
                continue
            # Wall time is the deadline; separate process CPU is the cost
            # sample. Wall elapsed time must never be presented as CPU work.
            start_wall_ns = perf_counter_ns()
            start_cpu_ns = process_time_ns()
            report = benchmark_synthetic_candidate(
                store, problem, candidate, curriculum.train, curriculum.heldout)
            elapsed_cpu_ns = process_time_ns() - start_cpu_ns
            elapsed_wall_ns = perf_counter_ns() - start_wall_ns
            budget_ns = problem.budget[1] * 1_000_000_000
            if (elapsed_wall_ns < 0 or elapsed_cpu_ns < 0
                    or elapsed_wall_ns > budget_ns
                    or elapsed_cpu_ns > budget_ns):
                held.append((candidate.candidate_sha256,
                             "LOCAL_SYNTHETIC_BENCHMARK_RESOURCE_BUDGET"))
                continue
            measured_ms = (elapsed_cpu_ns + 999_999) // 1_000_000
            # A plugin/test-double or stale interpreter result may carry
            # 2.0 == 2 or a different claimed B0 engine. A synthetic PASS
            # label alone must not enter cumulative research ranking.
            valid = (
                type(report) is SyntheticB1Benchmark
                and report.status == "B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED"
                and report.candidate_sha256 == candidate.candidate_sha256
                and report.baseline_sha256 == "LEGACY_RECONCILE_CSV_UNPINNED"
                and all(type(value) is int for value in (
                    report.train_count, report.heldout_count,
                    report.b0_train_matches, report.b0_heldout_matches,
                    report.b1_train_compared, report.b1_heldout_compared))
                and report.train_count == len(curriculum.train)
                and report.heldout_count == len(curriculum.heldout)
                and report.b0_train_matches == len(curriculum.train)
                and report.b0_heldout_matches == len(curriculum.heldout)
                and report.b1_train_compared == len(curriculum.train)
                and report.b1_heldout_compared == len(curriculum.heldout)
                and report.external_truth_verified is False
                and report.permission_to_learn is False
                and report.permission_to_promote is False
                and report.measured_runtime_uplift == "NOT_MEASURED"
            )
            if not valid:
                held.append((candidate.candidate_sha256,
                             "INDEPENDENT_SYNTHETIC_PARITY_NOT_ESTABLISHED"))
                continue
            scored.append(SyntheticStrategyScore(
                candidate.candidate_sha256, report.status,
                report.b1_train_compared, report.b1_heldout_compared,
                candidate.step_count, candidate.predicted_seconds,
                measured_synthetic_cpu_ms=measured_ms))
        except (ValueError, KeyError):
            held.append((candidate.candidate_sha256,
                         "SYNTHETIC_CANDIDATE_RECHECK_REJECTED"))
    # The candidate ranking uses observed local process CPU as its primary
    # *research-only* cost; estimated resource limits remain hard constraints.
    # Timing cannot assert real-world correctness or future performance.
    scored.sort(key=lambda item: (
        item.measured_synthetic_cpu_ms
        if item.measured_synthetic_cpu_ms is not None else 300001,
        item.declared_seconds, item.declared_steps, item.candidate_sha256))
    return StrategyRankingPreview(
        "SYNTHETIC_COST_ORDER_ONLY_NOT_LEARNING" if scored
        else "HOLD_NO_RECHECKED_SYNTHETIC_STRATEGY",
        problem.digest(), curriculum.manifest_sha256,
        tuple(scored), tuple(held))


# EAI-SWU-024/026: keep ranking and speculative CPU prior separate from trust.
@dataclass(frozen=True)
class LocalResearchRanking:
    problem_sha256: str
    status: str
    cost_order: tuple[str, ...]
    declined: tuple[tuple[str, str], ...]
    independent_ood_verified: bool = False
    trained_for_real_use: bool = False
    permits_execution: bool = False
    permits_promotion: bool = False
    # Research-only supplementary observations; not validated production timing.
    measured_synthetic_cpu_ms: tuple[tuple[str, int], ...] = ()
    research_cost_prior_sha256: tuple[str, ...] = ()
    research_prior: BoundedResearchPrior | None = None
    research_update_status: str = "NOT_REQUESTED"


def rank_bounded_strategy_research(
    store: AXNodeStore, problem: ProblemSpec,
    candidates: tuple[SynthesisCandidate, ...],
    curriculum: SyntheticCurriculum,
    *, prior: BoundedResearchPrior | None = None,
    update_research: bool = False,
) -> LocalResearchRanking:
    """Actual synthetic CPU ranking -> cost envelope; out-of-domain is HOLD."""
    if type(update_research) is not bool:
        raise ValueError("explicit typed research-only update switch required")
    if prior is not None and type(prior) is not BoundedResearchPrior:
        raise ValueError("typed previously research-only state required")
    if prior is not None and not update_research:
        raise ValueError("untrusted prior cannot be echoed without rechecking")
    from .strategy_cost_stats import build_bounded_strategy_cost_envelope
    reviewed = rank_synthetic_strategy_previews(
        store, problem, candidates, curriculum)
    from .strategy_learner import (
        ResearchStrategyObservation, derive_synthetic_strategy_prior)
    envelopes = build_bounded_strategy_cost_envelope(
        reviewed.ranked, max_steps=problem.budget[0],
        max_seconds=problem.budget[1])
    for entry in envelopes:
        observation = ResearchStrategyObservation(
            entry.candidate_sha256,
            entry.step_upper_bound, entry.second_upper_bound,
            "synthetic.cost.v1")
        local_cost_preview = derive_synthetic_strategy_prior(
            entry.candidate_sha256, (observation,),
            update_research_prior=True)
        if (local_cost_preview.can_train_trusted_model
                or local_cost_preview.accuracy_established):
            raise ValueError("unverified local CPU prior exceeded authority")
    measured = tuple(sorted((
        score.candidate_sha256, score.measured_synthetic_cpu_ms
    ) for score in reviewed.ranked
        if score.measured_synthetic_cpu_ms is not None))
    # Do not shadow the caller's BoundedResearchPrior with individual
    # ResearchStrategyUpdate previews in the loop above.
    new_prior, change = prior, "NOT_REQUESTED"
    if update_research:
        # A true bounded CPU update re-evaluates both B0 and B1 independently.
        # Failed/repeated/over-budget rounds return the SAME prior reference.
        update = advance_bounded_research_prior(
            store, problem, candidates, curriculum, prior)
        new_prior, change = update.prior, update.status
        if not update.accepted and prior is not None and new_prior != prior:
            raise ValueError("failed research update mutated prior")
        if update.accepted and (
                new_prior.trusted_training_permitted
                or new_prior.active_promotion_permitted
                or new_prior.independent_real_world_truth):
            raise PermissionError("synthetic observation widened authority")
    return LocalResearchRanking(
        problem.digest(),
        "SYNTHETIC_CPU_COST_ORDER_NOT_TRAINED" if envelopes
        else "HOLD_NO_SYNTHETIC_STRATEGY",
        tuple(item.candidate_sha256 for item in envelopes),
        reviewed.held, measured_synthetic_cpu_ms=measured,
        research_cost_prior_sha256=(
            () if new_prior is None else new_prior.curriculum_sha256),
        research_prior=new_prior, research_update_status=change)


def rank_verified_strategies(
    store: AXNodeStore, problem: ProblemSpec,
    candidates: tuple[SynthesisCandidate, ...],
    cases: tuple[ReconciliationCase, ...],
    reviews: tuple[SignedReconciliationReview, ...],
    journal: CandidateReviewJournal,
) -> VerifiedStrategyUpdate:
    """Fit from fresh verified episodes under the current owner policy.

    Admission, fit and held-out comparison share a journal transaction with
    policy updates. Failed admission or fitting rolls back journal writes.
    Reopen or roll back through the same journal. The selection is usable
    only until its earliest review expires and under its current owner policy.
    """
    with _admitting_verified_episodes(
        store, problem, candidates, cases, reviews, journal,
    ) as (policy, batch):
        update = _fit_verified_strategy(candidates, batch)
        selection = journal._write_selection(
            policy, candidate=update.advisory_candidate_sha256,
            fallback=update.fallback_candidate_sha256, valid_until=update.valid_until,
            proofs=batch.journal_entry_sha256)
        return replace(update, selection_sha256=selection.selection_sha256)
