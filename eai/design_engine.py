"""Deterministic, non-executing alternatives from provenance-labelled AXNODEs.

Two different local candidates are needed; otherwise the engine abstains.
A design is always UNVERIFIED until a separate independent verifier exists.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import CognitiveResult, DesignSpec, ProblemSpec
from .problem_model import ProblemAnalysis, ProblemModeler


@dataclass(frozen=True)
class DesignOutcome:
    analysis: ProblemAnalysis
    design: DesignSpec
    result: CognitiveResult


class DesignEngine:
    def __init__(self, modeler: ProblemModeler):
        if type(modeler) is not ProblemModeler:
            raise ValueError("local ProblemModeler required")
        self._modeler = modeler

    def propose(self, problem: ProblemSpec) -> DesignOutcome:
        analysis = self._modeler.analyze(problem)
        reason = ""
        if analysis.contradictions:
            reason = "CONTRADICTORY_HARD_CONSTRAINTS"
        elif analysis.state == "BLOCKED_UNINTERPRETED_CONSTRAINT":
            reason = "UNINTERPRETED_HARD_CONSTRAINTS"
        elif any(u.startswith("ambiguous_strategy_version:") for u in analysis.unknowns):
            reason = "AMBIGUOUS_STRATEGY_VERSION"
        elif any(u.startswith("required_strategy_missing:") for u in analysis.unknowns):
            reason = "REQUIRED_STRATEGY_NOT_AVAILABLE"
        elif len(analysis.evidence) < 2:
            reason = "INSUFFICIENT_DISTINCT_LOCAL_STRATEGIES"
        elif len(analysis.evidence) - len(analysis.required) < (1 if analysis.required else 2):
            # Two alternative designs must EACH honor every mandatory strategy.
            # Never drop a required strategy merely to manufacture variety.
            reason = "INSUFFICIENT_OPTIONAL_STRATEGIES"
        elif problem.risk == "HIGH":
            reason = "HIGH_RISK_REQUIRES_INDEPENDENT_REVIEW"
        options: list[dict] = []
        if not reason:
            required = list(analysis.required)
            optional = [entry for entry in analysis.evidence
                        if entry.strategy_id not in analysis.required]
            if len(optional) >= 2:
                first_refs = required + [optional[0].strategy_id]
                second_refs = required + [optional[1].strategy_id]
            elif len(optional) == 1 and required:
                first_refs = required
                second_refs = required + [optional[0].strategy_id]
            else:
                first_refs = [optional[0].strategy_id]
                second_refs = [optional[1].strategy_id]
            if (first_refs == second_refs or
                    not set(analysis.required).issubset(first_refs) or
                    not set(analysis.required).issubset(second_refs) or
                    any(ref in analysis.forbidden for ref in first_refs + second_refs)):
                raise ValueError("alternative violates required or forbidden strategies")
            options = [
                {
                    "id": "option.evidence_first",
                    "strategy_refs": first_refs,
                    "tradeoffs": ["Local candidate only; relevance not independently proven",
                                  "Source hash pinned; no execution or promotion"],
                    "verification": "Independent heldout oracle and source recheck required",
                },
                {
                    "id": "option.alternative_source",
                    "strategy_refs": second_refs,
                    "tradeoffs": ["Distinct strategy candidate; unknown real-world utility",
                                  "No network or original-data mutation"],
                    "verification": "Compare constraints and counterexamples before use",
                },
            ]
        design = DesignSpec.validate({
            "version": 1, "problem_sha256": analysis.problem_sha256,
            "alternatives": options, "blocked_reason": reason,
        })
        result = CognitiveResult.validate({
            "version": 1,
            "status": "CONFLICT" if analysis.contradictions else "UNVERIFIED",
            "problem_sha256": analysis.problem_sha256,
            "evidence_sha256": [candidate.source_sha256 for candidate in
                                analysis.evidence if candidate.source_sha256][0:32],
            "unknowns": list(analysis.unknowns),
        })
        return DesignOutcome(analysis, design, result)


# EAI-SWU-013: bridge a modeled problem to evidence-bound design alternatives.
@dataclass(frozen=True)
class DesignObligation:
    alternative_id: str
    node_source_sha256: tuple[str, ...]
    tradeoffs: tuple[str, ...]
    verification_required: str
    status: str = "ADVISORY_UNVERIFIED"


@dataclass(frozen=True)
class DesignReview:
    problem_sha256: str
    status: str
    alternatives: tuple[DesignObligation, ...]
    reason_codes: tuple[str, ...]
    unknown_count: int
    verified: bool = False
    permits_execution: bool = False


def review_design_alternatives(
    engine: DesignEngine, problem: ProblemSpec,
) -> DesignReview:
    """Actual local modeler -> design -> source obligations; never a proof."""
    if type(engine) is not DesignEngine or type(problem) is not ProblemSpec:
        raise ValueError("explicit EAI design engine and typed problem required")
    outcome = engine.propose(problem)
    digest = problem.digest()
    if (outcome.analysis.problem_sha256 != digest or
            outcome.design.problem_sha256 != digest or
            outcome.result.problem_sha256 != digest):
        raise ValueError("cross-problem design outcome")
    if outcome.result.status not in ("UNVERIFIED", "CONFLICT"):
        raise ValueError("model cannot establish independent verification")
    evidence = {e.strategy_id: e.source_sha256 for e in outcome.analysis.evidence}
    blockers = []
    if outcome.design.blocked_reason:
        blockers.append("DESIGN_BLOCKED")
    if outcome.analysis.contradictions:
        blockers.append("HARD_CONSTRAINT_CONFLICT")
    obligations = []
    for aid, refs, tradeoffs, check in outcome.design.alternatives:
        if (not refs or len(refs) > 8 or len(set(refs)) != len(refs)
                or not set(refs).issubset(evidence)
                or not set(outcome.analysis.required).issubset(refs)
                or set(refs) & set(outcome.analysis.forbidden)):
            raise ValueError("design option is not grounded in local candidates")
        pinned = tuple(evidence[r] for r in refs)
        if len(set(pinned)) != len(pinned):
            raise ValueError("duplicated AXNODE source in design")
        obligations.append(DesignObligation(
            aid, pinned, tradeoffs, check))
    if len(obligations) != 2 or obligations[0].node_source_sha256 == obligations[1].node_source_sha256:
        blockers.append("TWO_DISTINCT_ALTERNATIVES_NOT_ESTABLISHED")
    if not blockers:
        blockers.append("INDEPENDENT_ORACLE_PENDING")
    held = any(code != "INDEPENDENT_ORACLE_PENDING" for code in blockers)
    return DesignReview(
        digest, "ABSTAINED" if held else "TWO_ALTERNATIVES_UNVERIFIED",
        tuple(obligations) if not held else (),
        tuple(sorted(set(blockers))), len(outcome.analysis.unknowns))
