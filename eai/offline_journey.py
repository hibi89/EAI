"""EAI V3 local Architect -> PolicyGate -> CPU budget -> pure Player journey.

This is a safe integration of existing EAI-owned components, not an autonomous
real-world worker. Real AXNODE operators are never dispatched. Only explicitly
requested 'synthetic.noop.v1' steps can be interpreted after revalidation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
import hashlib
from time import monotonic_ns

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


def _check_cancel(cancel_check: Callable[[], bool] | None) -> None:
    """Fail closed at bounded journey stage boundaries; never run side effects."""
    if cancel_check is None:
        return
    cancelled = cancel_check()
    if type(cancelled) is not bool:
        raise ValueError("cancellation callback must return bool")
    if cancelled:
        raise ValueError("offline journey cancelled before publishing a result")


def _check_postflight(problem: ProblemSpec, plan: PlanSpec,
                      budget: LocalResourceBudget, started_ns: int) -> None:
    """No synthetic success receipt if the final measured budget was exceeded."""
    elapsed_ms = (monotonic_ns() - started_ns) // 1_000_000
    if elapsed_ms < 0:
        raise ValueError("invalid monotonic journey duration")
    postflight = observe_plan_resource_preflight(
        problem, plan, budget, elapsed_ms=elapsed_ms, steps_completed=0)
    if postflight.status != "PURE_SYNTHETIC_PLAN_PREFLIGHT_ONLY":
        raise ValueError("post-interpretation resource budget not established")


def preview_offline_journey(
    problem_file: str | Path, axnode_root: str | Path, *,
    max_expansions: int = 8,
    budget: LocalResourceBudget | None = None,
    interpret_pure_noop: bool = False,
    research_policy: ResearchPolicy | None = None,
    cancel_check: Callable[[], bool] | None = None,
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
    if cancel_check is not None and not callable(cancel_check):
        raise ValueError("explicit local cancellation callback required")
    _check_cancel(cancel_check)
    # Existing Architect independently confirms local store/schema constraints
    # and refuses to auto-create a customer-selected path.
    started_ns = monotonic_ns()
    source = preview_architecture(
        problem_file, axnode_root, max_expansions=max_expansions)
    _check_cancel(cancel_check)
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
            _check_cancel(cancel_check)
            if type(option) is not dict:
                raise ValueError("invalid architect alternative")
            node_hashes = tuple(option["node_hashes"])
            step_sources = option.get("step_sources")
            if (type(step_sources) is not list
                    or len(step_sources) != len(option["plan_steps"])):
                raise ValueError("unbound plan source inventory")
            bound_steps = set()
            source_inventory = {pinned: [] for pinned in node_hashes}
            for step, source_item in zip(option["plan_steps"], step_sources):
                if (type(step) is not dict or type(source_item) is not dict
                        or set(source_item) != {"step", "axnode_sha256"}
                        or source_item["step"] != step.get("id")
                        or source_item["step"] in bound_steps
                        or source_item["axnode_sha256"] not in node_hashes):
                    raise ValueError("plan step is not pinned to AXNODE provenance")
                bound_steps.add(source_item["step"])
                source_inventory[source_item["axnode_sha256"]].append(
                    (step.get("operator"), step.get("capability")))
            for pinned in node_hashes:
                node = store.get(pinned)
                if node.sha256 != pinned:
                    raise ValueError("stale pinned AXNODE")
                # Match the *ordered* operator inventory and minimum capability
                # to the content-addressed source; a caller-modified preview
                # must not launder a real step into synthetic.noop.v1.
                raw = node.as_dict()
                expected = [
                    (entry["skill"], "local.read"
                     if entry["skill"] == "csv.reconcile.v1" else "pure")
                    for entry in raw["steps"]
                ]
                if source_inventory[pinned] != expected:
                    raise ValueError("plan operator/capability not bound to pinned AXNODE")
            plan = PlanSpec.validate({
                "version": 1,
                "problem_sha256": digest,
                "steps": option["plan_steps"],
                "budget": {"max_steps": problem.budget[0],
                           "max_seconds": problem.budget[1]},
            })
            if (option["declared_step_count"] != len(plan.steps)
                    or type(option["declared_seconds_upper_bound"]) is not int
                    or not 1 <= option["declared_seconds_upper_bound"] <= problem.budget[1]):
                raise ValueError("untrusted declared plan resource requirements")
            gate = evaluate_plan_policy(problem, plan)
            elapsed_ms = (monotonic_ns() - started_ns) // 1_000_000
            if elapsed_ms < 0:
                raise ValueError("invalid monotonic journey duration")
            observation = observe_plan_resource_preflight(
                problem, plan, budget, elapsed_ms=elapsed_ms,
                steps_completed=0)
            reasons = set(gate.reason_codes) | set(observation.reason_codes)
            status = "POLICY_OR_RESOURCE_HELD"
            trace = None
            steps = 0
            if (gate.disposition == "PURE_SYNTHETIC_PREVIEW_ONLY"
                    and observation.status == "PURE_SYNTHETIC_PLAN_PREFLIGHT_ONLY"):
                if interpret_pure_noop:
                    _check_cancel(cancel_check)
                    # Recheck immediately before the bounded in-memory Player.
                    # Reading AXNODEs or later options may consume the budget.
                    pre_execute = observe_plan_resource_preflight(
                        problem, plan, budget,
                        elapsed_ms=(monotonic_ns() - started_ns) // 1_000_000,
                        steps_completed=0)
                    if pre_execute.status != "PURE_SYNTHETIC_PLAN_PREFLIGHT_ONLY":
                        reasons.update(pre_execute.reason_codes)
                    else:
                        receipt = execute_pure_synthetic_preview(
                            problem, plan, gate)
                        replay = audit_pure_player_trace(
                            problem, plan, gate, receipt)
                        if replay.status != "PURE_TRACE_REPLAY_MATCH_UNVERIFIED":
                            raise ValueError("pure interpreter replay disagreement")
                        _check_postflight(problem, plan, budget, started_ns)
                        _check_cancel(cancel_check)
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
    _check_cancel(cancel_check)
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


def audit_offline_journey_report(report: dict) -> dict:
    """Untrusted report integrity and status cross-check, NOT authentication.

    Anyone can compute a hash, so digest agreement is not verified execution.
    This prevents accidental uplift/training/permission claims when archiving a
    purely synthetic status report.
    """
    from .contracts import canonical_sha256
    if (type(report) is not dict
            or set(report) != {
                "schema", "problem_sha256", "architect_status", "truth_status",
                "unknown_count", "contradiction_count",
                "evidence_review_required", "candidate_count", "candidates",
                "run_mode", "research_mode_status", "research_candidates_admitted",
                "network", "real_tool_invocations", "original_writes",
                "live_provider_invocations", "verified_real_world",
                "automatic_learning", "active_promotion", "receipt_sha256",
            }
            or report["schema"] != "eai.offline.journey.v1"
            or report["network"] != "DISABLED_BY_DESIGN"
            or report["research_mode_status"] not in ("OFF", "PAUSED_POLICY")
            or report["research_candidates_admitted"] != 0
            or report["real_tool_invocations"] != 0
            or report["original_writes"] != 0
            or report["live_provider_invocations"] != 0
            or report["verified_real_world"] is not False
            or report["automatic_learning"] is not False
            or report["active_promotion"] is not False
            or report["run_mode"] not in (
                "PURE_SYNTHETIC_EXPLICIT", "POLICY_RESOURCE_PREVIEW_ONLY")
            or type(report["candidate_count"]) is not int
            or not 0 <= report["candidate_count"] <= 8
            or type(report["candidates"]) is not list
            or len(report["candidates"]) != report["candidate_count"]):
        raise ValueError("unsafe or tampered journey envelope")
    import re
    _DIGEST = re.compile(r"[0-9a-f]{64}\Z")
    if (type(report["problem_sha256"]) is not str
            or not _DIGEST.fullmatch(report["problem_sha256"])
            or type(report["receipt_sha256"]) is not str
            or not _DIGEST.fullmatch(report["receipt_sha256"])):
        raise ValueError("invalid journey SHA")
    if (type(report["unknown_count"]) is not int
            or not 0 <= report["unknown_count"] <= 32
            or type(report["contradiction_count"]) is not int
            or not 0 <= report["contradiction_count"] <= 32
            or type(report["evidence_review_required"]) is not bool):
        raise ValueError("invalid uncertainty counters")
    for candidate in report["candidates"]:
        if (type(candidate) is not dict
                or set(candidate) != {
                    "alternative_id", "plan_sha256", "node_hashes", "status",
                    "reason_codes", "declared_steps", "declared_seconds",
                    "trace_sha256", "interpreted_steps", "original_writes",
                    "external_actions", "grants_real_authority",
                }
                or candidate["status"] not in (
                    "PURE_ELIGIBLE_NOT_INTERPRETED",
                    "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED",
                    "POLICY_OR_RESOURCE_HELD")
                or type(candidate["alternative_id"]) is not str
                or not 1 <= len(candidate["alternative_id"]) <= 64
                or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_.-"
                       for ch in candidate["alternative_id"])
                or type(candidate["node_hashes"]) is not list
                or len(set(candidate["node_hashes"])) != len(candidate["node_hashes"])
                or candidate["original_writes"] != 0
                or candidate["external_actions"] != 0
                or candidate["grants_real_authority"] is not False
                or type(candidate["plan_sha256"]) is not str
                or not _DIGEST.fullmatch(candidate["plan_sha256"])
                or type(candidate["node_hashes"]) is not list
                or not 1 <= len(candidate["node_hashes"]) <= 8
                or any(type(h) is not str or not _DIGEST.fullmatch(h)
                       for h in candidate["node_hashes"])
                or type(candidate["reason_codes"]) is not list
                or any(type(x) is not str or not x
                       or len(x) > 80 or not x.replace("_", "").isalnum()
                       or not x.isupper() for x in candidate["reason_codes"])
                or type(candidate["declared_steps"]) is not int
                or not 1 <= candidate["declared_steps"] <= 64
                or type(candidate["declared_seconds"]) is not int
                or not 1 <= candidate["declared_seconds"] <= 300
                or type(candidate["interpreted_steps"]) is not int
                or not 0 <= candidate["interpreted_steps"] <= candidate["declared_steps"]):
            raise ValueError("invalid journey candidate")
        executed = candidate["status"] == "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED"
        if ((candidate["status"] == "PURE_ELIGIBLE_NOT_INTERPRETED"
             and candidate["reason_codes"])
                or (candidate["status"] == "POLICY_OR_RESOURCE_HELD"
                    and not candidate["reason_codes"])):
            raise ValueError("journey candidate reason/status inconsistency")
        if (executed and (
                report["run_mode"] != "PURE_SYNTHETIC_EXPLICIT"
                or candidate["interpreted_steps"] != candidate["declared_steps"]
                or candidate["reason_codes"]
                or type(candidate["trace_sha256"]) is not str
                or not _DIGEST.fullmatch(candidate["trace_sha256"]))
                or (not executed and
                    (candidate["interpreted_steps"] != 0
                     or candidate["trace_sha256"] is not None))):
            raise ValueError("contradictory player interpretation claim")
    claimed = report["receipt_sha256"]
    content = {k: v for k, v in report.items() if k != "receipt_sha256"}
    if canonical_sha256(content) != claimed:
        raise ValueError("journey payload checksum mismatch")
    return {
        "status": "LOCAL_JOURNEY_DIGEST_INTEGRITY_UNVERIFIED",
        "receipt_sha256": claimed,
        "candidate_count": report["candidate_count"],
        "grants_real_authority": False,
        "independent_verification": "NOT_ESTABLISHED",
    }
