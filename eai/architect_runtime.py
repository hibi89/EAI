"""Explicit local-only V3 architect preview; no actions, remote model or writes to originals."""
from __future__ import annotations

from pathlib import Path

from .axnode_store import AXNodeStore
from .axnode_retrieval import AXNodeRetriever
from .contracts import MAX_DOCUMENT_BYTES, ProblemSpec, strict_json
from .design_engine import DesignEngine
from .problem_model import ProblemModeler
from .hierarchical_planner import HierarchicalPlanner
from .evidence_ledger import EvidenceLedger
from .local_files import local_path, read_bytes


def preview_architecture(problem_file: str | Path, axnode_root: str | Path, *,
                         max_expansions: int = 8, cancelled=None) -> dict:
    """Analyze a separately supplied bounded ProblemSpec against one local store.

    Catalog and evidence queries run on private snapshots. Node bodies are
    hash-checked at their source. Opening a preview never builds source indexes.
    """
    source = local_path(problem_file)
    if source.is_symlink() or not source.is_file():
        raise ValueError("explicit ordinary local problem file required")
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError("problem file exceeds strict JSON byte limit")
    raw = strict_json(read_bytes(source, MAX_DOCUMENT_BYTES))
    problem = ProblemSpec.validate(raw)
    return preview_architecture_problem(problem, axnode_root,
                                        max_expansions=max_expansions, cancelled=cancelled)


def preview_architecture_problem(problem: ProblemSpec, axnode_root: str | Path, *,
                                 max_expansions: int = 8, cancelled=None) -> dict:
    """In-memory, owner-reviewed ProblemSpec to the existing *real* Architect.

    No temp ProblemSpec or library write, no implicit library creation, and no
    generative approximation of strategy evidence. Existing safety checks stay.
    """
    if type(problem) is not ProblemSpec:
        raise ValueError("typed validated ProblemSpec required")
    # A frozen dataclass is not itself proof that its fields passed validate():
    # callers may construct or dataclasses.replace a forged ProblemSpec. Reject
    # before opening any AXNODE content or evidence sidecar.
    from .policy_gate import _validated_problem
    problem = _validated_problem(problem)
    root = local_path(axnode_root)
    if (root.is_symlink() or not root.is_dir() or
            not (root / "axnodes.sqlite").is_file() or
            (root / "axnodes.sqlite").is_symlink() or
            (root / "nodes").is_symlink() or
            not (root / "nodes").is_dir()):
        raise ValueError("existing explicit AXNODE library required; no auto-create")
    with AXNodeStore(root, read_only=True) as store:
        designer = DesignEngine(ProblemModeler(AXNodeRetriever(store)))
        design = designer.propose(problem)
        plans = HierarchicalPlanner(store).plan(
            problem, design, max_expansions=max_expansions, cancelled=cancelled)
        claim_states = []
        ledger_path = store.root / "evidence_ledger.sqlite"
        if ledger_path.exists() or ledger_path.is_symlink():
            # Existing local sidecar is examined read-only; NEVER auto-create it
            # merely to preview a user's private ProblemSpec.
            with EvidenceLedger(store) as evidence:
                for item in design.analysis.evidence:
                    assessed = evidence.assess(item.strategy_id)
                    claim_states.append({
                        "id": assessed.claim_id, "state": assessed.state,
                        "trust": assessed.trust,
                        "source_count": len(assessed.supporting_hashes) +
                                        len(assessed.refuting_hashes) +
                                        len(assessed.stale_hashes),
                    })
        evidence_disputed = any(
            item["state"] in ("CONTRADICTED_UNVERIFIED", "REFUTED_UNVERIFIED")
            for item in claim_states)
        # Untrusted observations cannot grant trust, but an explicit negative
        # or contradictory local report can safely force review.
        preview_status = "BLOCKED_EVIDENCE_DISPUTE" if evidence_disputed else plans.status
        safe_candidates = () if evidence_disputed else plans.candidates
    return {
        "schema": "eai.architect.preview.v1",
        "problem_sha256": problem.digest(),
        "status": preview_status,
        "truth_status": design.result.status,
        "execution": "NOT_EXECUTED",
        "model": "LOCAL_CPU_ONLY",
        "analysis": {
            "state": design.analysis.state,
            "contradictions": list(design.analysis.contradictions),
            "unknowns": list(design.analysis.unknowns),
            "candidate_provenance": "LOCAL_CANDIDATE_UNVERIFIED",
        },
        "design_blocked_reason": design.design.blocked_reason,
        "option_obligations": [
            {"alternative_id": aid, "strategy_refs": list(refs),
             "tradeoffs": list(tradeoffs), "verification_required": verify}
            for aid, refs, tradeoffs, verify in design.design.alternatives
        ],
        "evidence_claims": claim_states,
        "evidence_review_required": evidence_disputed,
        "plan_search_expansions": plans.expansions,
        "blocked_alternatives": [
            {"id": aid, "reason": reason} for aid, reason in plans.blocked
        ] + ([{"id": "evidence", "reason": "UNTRUSTED_NEGATIVE_OR_CONFLICT"}]
             if evidence_disputed else []),
        "advisory_plans": [
            {
                "alternative_id": candidate.alternative_id,
                "status": candidate.trust,
                "node_hashes": list(candidate.node_hashes),
                "step_sources": [
                    {"step": sid, "axnode_sha256": sha}
                    for sid, sha in candidate.step_sources
                ],
                "plan_steps": [
                    {"id": sid, "operator": operator, "requires": list(deps),
                     "capability": cap}
                    for sid, operator, deps, cap in candidate.plan.steps
                ],
                "declared_step_count": candidate.declared_step_count,
                "declared_seconds_upper_bound": candidate.declared_seconds_upper_bound,
            } for candidate in safe_candidates
        ],
    }
