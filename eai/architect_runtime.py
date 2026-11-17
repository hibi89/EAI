"""Explicit local-only V3 architect preview; no actions, remote model or writes to originals."""
from __future__ import annotations

from pathlib import Path

from .axnode_store import AXNodeStore
from .axnode_retrieval import AXNodeRetriever
from .contracts import MAX_DOCUMENT_BYTES, ProblemSpec, strict_json
from .design_engine import DesignEngine
from .problem_model import ProblemModeler
from .hierarchical_planner import HierarchicalPlanner


def preview_architecture(problem_file: str | Path, axnode_root: str | Path, *,
                         max_expansions: int = 8) -> dict:
    """Analyze a separately supplied bounded ProblemSpec against one local store.

    The existing AXNODE SQLite/FTS indexes can be locally updated by open/search;
    no original customer sources, legacy EAI DB, network or tools are accessed.
    """
    source = Path(problem_file).expanduser()
    root = Path(axnode_root).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError("explicit ordinary local problem file required")
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError("problem file exceeds strict JSON byte limit")
    if (root.is_symlink() or not root.is_dir() or
            not (root / "axnodes.sqlite").is_file() or
            (root / "axnodes.sqlite").is_symlink() or
            (root / "nodes").is_symlink() or
            not (root / "nodes").is_dir()):
        raise ValueError("existing explicit AXNODE library required; no auto-create")
    raw = strict_json(source.read_bytes())
    problem = ProblemSpec.validate(raw)
    with AXNodeStore(root) as store:
        designer = DesignEngine(ProblemModeler(AXNodeRetriever(store)))
        design = designer.propose(problem)
        plans = HierarchicalPlanner(store).plan(
            problem, design, max_expansions=max_expansions)
    return {
        "schema": "eai.architect.preview.v1",
        "problem_sha256": problem.digest(),
        "status": plans.status,
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
        "plan_search_expansions": plans.expansions,
        "blocked_alternatives": [
            {"id": aid, "reason": reason} for aid, reason in plans.blocked
        ],
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
            } for candidate in plans.candidates
        ],
    }
