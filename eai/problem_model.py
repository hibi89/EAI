"""EAI-owned bounded problem modeling, never a remote or self-verifying brain.

The explicit `must:<id>` / `forbid:<id>` constraint language is intentionally
small: other natural language is UNKNOWN, never silently inferred as true.
AXNODE hits are unverified *candidate references*, not proof of applicability.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .contracts import ProblemSpec
from .axnode_retrieval import AXNodeRetriever, NodeMatch

_TOKEN = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_CANDIDATES = 8


@dataclass(frozen=True)
class CandidateEvidence:
    """Exact local candidate provenance, never an independent oracle receipt."""
    strategy_id: str
    source_sha256: str
    status: str = "UNVERIFIED"
    origin: str = "LOCAL_CANDIDATE_UNVERIFIED"
    freshness: str = "UNKNOWN"


@dataclass(frozen=True)
class ProblemAnalysis:
    problem_sha256: str
    state: str
    required: tuple[str, ...]
    forbidden: tuple[str, ...]
    contradictions: tuple[str, ...]
    unknowns: tuple[str, ...]
    evidence: tuple[CandidateEvidence, ...]


class ProblemModeler:
    """Read-only semantic boundary around existing versioned ProblemSpec."""

    def __init__(self, retriever: AXNodeRetriever):
        if type(retriever) is not AXNodeRetriever:
            raise ValueError("explicit local AXNODE retriever required")
        self._retriever = retriever

    def analyze(self, problem: ProblemSpec) -> ProblemAnalysis:
        if type(problem) is not ProblemSpec:
            raise ValueError("typed ProblemSpec required")
        required: set[str] = set()
        forbidden: set[str] = set()
        unknown: list[str] = []
        for index, clause in enumerate(problem.hard_constraints):
            if clause.startswith("must:") and _TOKEN.fullmatch(clause[5:]):
                required.add(clause[5:])
            elif clause.startswith("forbid:") and _TOKEN.fullmatch(clause[7:]):
                forbidden.add(clause[7:])
            else:
                unknown.append(f"constraint_unparsed:{index}")
        contradictions = tuple(sorted(required & forbidden))
        for index, _ in enumerate(problem.assumptions):
            unknown.append(f"assumption_unverified:{index}")
        for state_ref in problem.state_refs:
            unknown.append("state_unverified:" + state_ref)
        unknown.append("oracle_unverified")
        if problem.risk == "HIGH":
            unknown.append("high_risk_review_required")
        # Search a validated public identifier, not raw goals or private state.
        found = self._retriever.find(problem.domain, limit=_MAX_CANDIDATES)
        if type(found) is not tuple or len(found) > _MAX_CANDIDATES:
            raise ValueError("invalid bounded AXNODE result")
        evidence: list[CandidateEvidence] = []
        distinct_ids: set[str] = set()
        for candidate in found:
            if (type(candidate) is not NodeMatch or
                    type(candidate.node_id) is not str or
                    not _TOKEN.fullmatch(candidate.node_id) or
                    type(candidate.sha256) is not str or
                    not _SHA.fullmatch(candidate.sha256) or
                    candidate.status not in ("DRAFT", "CANDIDATE") or
                    candidate.provenance != "LOCAL_CANDIDATE_UNVERIFIED"):
                raise ValueError("untrusted or malformed AXNODE candidate")
            if candidate.node_id in distinct_ids:
                unknown.append("ambiguous_strategy_version:" + candidate.node_id)
                continue
            distinct_ids.add(candidate.node_id)
            if candidate.node_id not in forbidden:
                evidence.append(CandidateEvidence(candidate.node_id, candidate.sha256))
        missing_required = required - {entry.strategy_id for entry in evidence}
        for strategy in sorted(missing_required):
            unknown.append("required_strategy_missing:" + strategy)
        if not evidence:
            unknown.append("no_local_candidate")
        if len(evidence) < 2:
            unknown.append("independent_alternatives_insufficient")
        state = "CONFLICT" if contradictions else (
            "BLOCKED_UNINTERPRETED_CONSTRAINT" if any(
                item.startswith("constraint_unparsed:") for item in unknown) else
            "CANDIDATES_UNVERIFIED")
        return ProblemAnalysis(
            problem.digest(), state, tuple(sorted(required)),
            tuple(sorted(forbidden)), contradictions,
            tuple(dict.fromkeys(unknown))[:32], tuple(evidence))


# EAI P1 SWU 003: classified input -> bounded CPU-owned V3 ProblemSpec.
from hashlib import sha256
from .intent import OptionalInputParser, QwenIntentParser


@dataclass(frozen=True)
class InputProblemModel:
    problem: ProblemSpec
    input_source: str
    input_task: str
    status: str


def model_local_problem_input(text: str, *,
                              use_qwen: bool = False,
                              qwen_parser: QwenIntentParser | None = None
                              ) -> InputProblemModel:
    """Never infer actions, permissions, verification or evidence from model text."""
    if (type(text) is not str or not 1 <= len(text.strip()) <= 1200 or
            any(ord(ch) < 32 and ch not in "\n\t" for ch in text)):
        raise ValueError("bounded local input text required")
    parsed = OptionalInputParser(qwen_parser).parse(text, use_qwen=use_qwen)
    domain = {
        "calculate": "arithmetic", "compare": "comparison",
        "help": "capability", "recall": "memory", "notes": "memory",
        "search": "research", "remember": "memory",
    }.get(parsed.intent.task, "unknown")
    identifier = "input." + sha256(text.encode("utf-8")).hexdigest()[:24]
    problem = ProblemSpec.validate({
        "version": 1, "id": identifier, "goal": text.strip(),
        "domain": domain, "state_refs": [], "assumptions": [],
        "hard_constraints": [], "objectives": ["examine_input_only"],
        "oracle": "unverified.cpu.review", "permissions": ["pure"],
        "budget": {"max_steps": 8, "max_seconds": 30}, "risk": "MEDIUM",
    })
    return InputProblemModel(
        problem, parsed.source, parsed.intent.task,
        "INPUT_CLASSIFIED_UNVERIFIED" if parsed.intent.task != "unsupported"
        else "NEEDS_EXPLICIT_PROBLEM_SPEC")


# EAI-SWU-012: link unresolved constraints to explicit CPU decision abstention.
@dataclass(frozen=True)
class ProblemDecisionReadiness:
    problem_sha256: str
    disposition: str
    reason_codes: tuple[str, ...]
    candidate_source_sha256: tuple[str, ...]
    unknowns: tuple[str, ...]
    independent_verification: str = "NOT_ESTABLISHED"
    executable: bool = False


def review_problem_decision(
    modeler: ProblemModeler, problem: ProblemSpec,
) -> ProblemDecisionReadiness:
    """Do not treat ambiguous AXNODE matches or unknown facts as evidence."""
    if type(modeler) is not ProblemModeler or type(problem) is not ProblemSpec:
        raise ValueError("typed local modeler and problem required")
    analysis = modeler.analyze(problem)
    if analysis.problem_sha256 != problem.digest():
        raise ValueError("cross-problem analysis rejected")
    blockers = []
    if analysis.contradictions or analysis.state == "CONFLICT":
        blockers.append("CONFLICTING_HARD_CONSTRAINTS")
    if analysis.state == "BLOCKED_UNINTERPRETED_CONSTRAINT" or any(
            u.startswith("constraint_unparsed:") for u in analysis.unknowns):
        blockers.append("UNINTERPRETED_HARD_CONSTRAINT")
    if any(u.startswith("ambiguous_strategy_version:")
           for u in analysis.unknowns):
        blockers.append("AMBIGUOUS_STRATEGY_VERSION")
    if any(u.startswith("required_strategy_missing:")
           for u in analysis.unknowns):
        blockers.append("REQUIRED_STRATEGY_MISSING")
    if len(analysis.evidence) < 2:
        blockers.append("INSUFFICIENT_ALTERNATIVE_EVIDENCE")
    if problem.risk == "HIGH":
        blockers.append("HIGH_RISK_REQUIRES_REVIEW")
    if not blockers:
        blockers.append("INDEPENDENT_ORACLE_NOT_ESTABLISHED")
    sources = tuple(item.source_sha256 for item in analysis.evidence)
    if len(set(sources)) != len(sources):
        blockers.append("DUPLICATE_SOURCE_EVIDENCE")
    holding = any(code != "INDEPENDENT_ORACLE_NOT_ESTABLISHED" for code in blockers)
    return ProblemDecisionReadiness(
        analysis.problem_sha256, "ABSTAINED" if holding else "ADVISORY_ONLY",
        tuple(sorted(set(blockers))), sources, analysis.unknowns)
