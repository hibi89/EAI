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
                first_refs = [analysis.evidence[0].strategy_id]
                second_refs = [analysis.evidence[1].strategy_id]
            if first_refs == second_refs:
                raise ValueError("cannot create distinct bounded alternatives")
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
