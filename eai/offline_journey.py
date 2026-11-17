"""EAI V3 local Architect -> PolicyGate -> CPU budget -> pure Player journey.

This is a safe integration of existing EAI-owned components, not an autonomous
real-world worker. Real AXNODE operators are never dispatched. Only explicitly
requested 'synthetic.noop.v1' steps can be interpreted after revalidation.
"""
from __future__ import annotations

from pathlib import Path
import hashlib

from .architect_runtime import preview_architecture
from .axnode_store import AXNodeStore
from .contracts import PlanSpec, ProblemSpec, canonical_bytes
from .local_scheduler import (
    LocalResourceBudget, observe_plan_resource_preflight)
from .player_cli import _read_local_contract
from .player_runtime import (
    execute_pure_synthetic_preview, audit_pure_player_trace)
from .policy_gate import evaluate_plan_policy
from .trace_renderer import render_architect_explanation
from .research_policy import ResearchPolicy
from .research_providers import ResearchCoordinator


def preview_offline_journey(
    problem_file: str | Path, axnode_root: str | Path, *,
    max_expansions: int = 8,
    budget: LocalResourceBudget | None = None,
    interpret_pure_noop: bool = False,
    research_policy: ResearchPolicy | None = None,
) -> dict:
    """Bounded full local decision path. Even a PASS gives zero real authority."""
    if type(interpret_pure_noop) is not bool:
        raise ValueError("explicit boolean synthetic interpretation switch")
    if research_policy is not None and type(research_policy) is not ResearchPolicy:
        raise ValueError("explicit typed offline research policy required")
    budget = (LocalResourceBudget(
        max_rss_mib=1024, max_elapsed_ms=300000, max_steps=64)
        if budget is None else budget)
    if type(budget) is not LocalResourceBudget:
        raise ValueError("explicit CPU budget required")
    # Existing Architect independently confirms local store/schema constraints
    # and refuses to auto-create a customer-selected path.
    source = preview_architecture(
        problem_file, axnode_root, max_expansions=max_expansions)
    # Research proposals cannot replace the independent OFF baseline. This
    # provider boundary stays inert in both OFF and simulated ON/paused modes.
    research = ResearchCoordinator(research_policy)
    fallback = research.evaluate(source)
    if fallback.baseline is not source or fallback.candidates:
        raise ValueError("external research changed original EAI baseline")
    if fallback.mode_status not in ("OFF", "PAUSED_POLICY"):
        raise ValueError("unrecognized optional research mode")
    explanation = render_architect_explanation(source)
    problem = ProblemSpec.validate(_read_local_contract(problem_file))
    digest = problem.digest()
    if explanation["problem_sha256"] != digest:
        raise ValueError("architect result cross-problem digest")
    if (explanation["execution"] != "NOT_EXECUTED"
            or explanation["verified_real_world"] is not False):
        raise ValueError("untrusted architect preview")
    plans = source["advisory_plans"]
    if (len(plans) != len(explanation["alternatives"]) or len(plans) > 8
            or any(p["alternative_id"] != e["alternative_id"]
                   for p, e in zip(plans, explanation["alternatives"]))):
        raise ValueError("inconsistent bounded architect alternatives")
    candidates = []
    # Reopen only the explicitly selected local source store. Never invoke
    # real tools or assume a prior preview was an approved execution request.
    with AXNodeStore(axnode_root) as store:
        for option in plans:
            if type(option) is not dict:
                raise ValueError("invalid architect alternative")
            node_hashes = tuple(option["node_hashes"])
            step_sources = option.get("step_sources")
            if (type(step_sources) is not list
                    or len(step_sources) != len(option["plan_steps"])):
                raise ValueError("unbound plan source inventory")
            bound_steps = set()
            for step, source_item in zip(option["plan_steps"], step_sources):
                if (type(step) is not dict or type(source_item) is not dict
                        or set(source_item) != {"step", "axnode_sha256"}
                        or source_item["step"] != step.get("id")
                        or source_item["step"] in bound_steps
                        or source_item["axnode_sha256"] not in node_hashes):
                    raise ValueError("plan step is not pinned to AXNODE provenance")
                bound_steps.add(source_item["step"])
            for pinned in node_hashes:
                node = store.get(pinned)
                if node.sha256 != pinned:
                    raise ValueError("stale pinned AXNODE")
            plan = PlanSpec.validate({
                "version": 1,
                "problem_sha256": digest,
                "steps": option["plan_steps"],
                "budget": {"max_steps": problem.budget[0],
                           "max_seconds": problem.budget[1]},
            })
            gate = evaluate_plan_policy(problem, plan)
            observation = observe_plan_resource_preflight(
                problem, plan, budget, elapsed_ms=0, steps_completed=0)
            reasons = set(gate.reason_codes) | set(observation.reason_codes)
            status = "POLICY_OR_RESOURCE_HELD"
            trace = None
            steps = 0
            if (gate.disposition == "PURE_SYNTHETIC_PREVIEW_ONLY"
                    and observation.status == "PURE_SYNTHETIC_PLAN_PREFLIGHT_ONLY"):
                if interpret_pure_noop:
                    receipt = execute_pure_synthetic_preview(
                        problem, plan, gate)
                    replay = audit_pure_player_trace(
                        problem, plan, gate, receipt)
                    if replay.status != "PURE_TRACE_REPLAY_MATCH_UNVERIFIED":
                        raise ValueError("pure interpreter replay disagreement")
                    status = "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED"
                    trace = replay.expected_trace_sha256
                    steps = replay.matching_steps
                else:
                    status = "PURE_ELIGIBLE_NOT_INTERPRETED"
            candidates.append({
                "alternative_id": option["alternative_id"],
                "plan_sha256": gate.plan_sha256,
                "node_hashes": list(node_hashes),
                "status": status,
                "reason_codes": sorted(reasons),
                "declared_steps": option["declared_step_count"],
                "declared_seconds": option["declared_seconds_upper_bound"],
                "trace_sha256": trace,
                "interpreted_steps": steps,
                "original_writes": 0,
                "external_actions": 0,
                "grants_real_authority": False,
            })
    report = {
        "schema": "eai.offline.journey.v1",
        "problem_sha256": digest,
        "architect_status": explanation["status"],
        "truth_status": explanation["truth_status"],
        "unknown_count": explanation["uncertainty"]["unknown_count"],
        "contradiction_count": explanation["uncertainty"]["contradiction_count"],
        "evidence_review_required": explanation["uncertainty"][
            "evidence_review_required"],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "run_mode": ("PURE_SYNTHETIC_EXPLICIT" if interpret_pure_noop
                     else "POLICY_RESOURCE_PREVIEW_ONLY"),
        "research_mode_status": fallback.mode_status,
        "research_candidates_admitted": 0,
        "network": "DISABLED_BY_DESIGN",
        "real_tool_invocations": 0,
        "original_writes": 0,
        "live_provider_invocations": 0,
        "verified_real_world": False,
        "automatic_learning": False,
        "active_promotion": False,
    }
    report["receipt_sha256"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    return report
