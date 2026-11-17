"""C24 EAI-owned digest-only explanations of unverified Architect/Player data.

Untrusted reports can contain private goals, file paths or injected Markdown.
This layer never renders those strings, HTML, external URLs or verified claims.
"""
from __future__ import annotations

import re

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_ARCHITECT_STATUS = frozenset({
    "CANDIDATES_UNVERIFIED", "PARTIAL_UNVERIFIED", "BLOCKED", "CANCELLED",
    "BLOCKED_EVIDENCE_DISPUTE"
})
_TRUTH = frozenset({"UNVERIFIED", "UNSUPPORTED", "CONFLICT"})
_STEP_OPERATORS = frozenset({
    "synthetic.noop.v1", "csv.reconcile.v1",
    "evidence.verify_receipt.v1"
})
_PLAYER_STATUS = frozenset({
    "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED",
    "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED",
    "HOLD_POLICY_DENIED",
})


def _hash(value: object) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("untrusted explanation SHA")
    return value


def _bounded_count(value: object, maximum: int = 64) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("untrusted explanation count")
    return value


def render_architect_explanation(raw: dict) -> dict:
    """Whitelisted summary; never echo analysis unknown text or raw evidence."""
    if (type(raw) is not dict or raw.get("schema") != "eai.architect.preview.v1"
            or raw.get("execution") != "NOT_EXECUTED"
            or raw.get("model") != "LOCAL_CPU_ONLY"
            or type(raw.get("status")) is not str
            or raw.get("status") not in _ARCHITECT_STATUS
            or type(raw.get("truth_status")) is not str
            or raw.get("truth_status") not in _TRUTH
            or type(raw.get("analysis")) is not dict
            or type(raw.get("advisory_plans")) is not list
            or len(raw["advisory_plans"]) > 8):
        raise ValueError("unsupported or privileged architect report")
    analysis = raw["analysis"]
    contradictions = analysis.get("contradictions")
    unknowns = analysis.get("unknowns")
    if (type(contradictions) is not list or len(contradictions) > 32
            or type(unknowns) is not list or len(unknowns) > 32
            or type(raw.get("evidence_review_required")) is not bool):
        raise ValueError("invalid architect uncertainty metadata")
    plans = []
    for candidate in raw["advisory_plans"]:
        if (type(candidate) is not dict
                or candidate.get("status") != "ADVISORY_UNVERIFIED_NOT_EXECUTED"
                or type(candidate.get("alternative_id")) is not str
                or not _ID.fullmatch(candidate["alternative_id"])
                or type(candidate.get("plan_steps")) is not list
                or not 1 <= len(candidate["plan_steps"]) <= 64
                or type(candidate.get("node_hashes")) is not list
                or not 1 <= len(candidate["node_hashes"]) <= 8):
            raise ValueError("untrusted plan candidate")
        sources = tuple(_hash(item) for item in candidate["node_hashes"])
        if len(set(sources)) != len(sources):
            raise ValueError("duplicate plan source")
        operators = []
        for step in candidate["plan_steps"]:
            if (type(step) is not dict or
                    type(step.get("operator")) is not str or
                    step["operator"] not in _STEP_OPERATORS):
                raise ValueError("untrusted plan operator")
            operators.append(step["operator"])
        plans.append({
            "alternative_id": candidate["alternative_id"],
            "step_count": len(operators),
            "operator_ids": operators,
            "source_sha256": list(sources),
            "status": "ADVISORY_UNVERIFIED_NOT_EXECUTED",
        })
    if (raw["status"] not in ("CANDIDATES_UNVERIFIED", "PARTIAL_UNVERIFIED")
            and plans):
        raise ValueError("blocked report cannot contain active candidates")
    if raw["status"] == "PARTIAL_UNVERIFIED" and len(plans) != 1:
        raise ValueError("partial architect report requires one advisory candidate")
    return {
        "schema": "eai.explanation.v1",
        "kind": "ARCHITECT",
        "status": raw["status"],
        "problem_sha256": _hash(raw.get("problem_sha256")),
        "truth_status": raw["truth_status"],
        "uncertainty": {
            "unknown_count": len(unknowns),
            "contradiction_count": len(contradictions),
            "evidence_review_required": raw["evidence_review_required"],
        },
        "alternatives": plans,
        "execution": "NOT_EXECUTED",
        "verified_real_world": False,
        "network": "DISABLED_BY_DESIGN",
    }


def render_player_explanation(raw: dict) -> dict:
    """No arbitrary raw receipts or task payloads are returned."""
    if (type(raw) is not dict
            or raw.get("schema") != "eai.player.preview.v1"
            or type(raw.get("status")) is not str
            or raw.get("status") not in _PLAYER_STATUS
            or raw.get("real_world_verified") is not False
            or raw.get("automatic_learning") is not False
            or raw.get("active_promotion") is not False):
        raise ValueError("untrusted or authorized-looking Player report")
    status = raw["status"]
    if status == "HOLD_POLICY_DENIED":
        if raw.get("execution") != "DENIED":
            raise ValueError("denied preview cannot claim execution")
        count = 0
        trace = None
    else:
        if (raw.get("execution") != "PURE_SYNTHETIC_NOOP_ONLY"
                or raw.get("external_actions") != 0
                or raw.get("original_writes") != 0):
            raise ValueError("unsupported Player side effects")
        trace = _hash(raw.get("trace_sha256"))
        count = _bounded_count(raw.get("interpreted_step_count"))
    return {
        "schema": "eai.explanation.v1", "kind": "PLAYER",
        "status": status,
        "problem_sha256": _hash(raw.get("problem_sha256")),
        "plan_sha256": _hash(raw.get("plan_sha256")),
        "trace_sha256": trace,
        "interpreted_steps": count,
        "execution": "DENIED" if status == "HOLD_POLICY_DENIED"
                     else "PURE_SYNTHETIC_NOOP_ONLY",
        "verified_real_world": False,
        "network": "DISABLED_BY_DESIGN",
    }

def render_explanation_text(raw: dict) -> str:
    """ASCII-safe offline terminal report, built from validated structured data."""
    if type(raw) is not dict or raw.get("schema") != "eai.explanation.v1":
        raise ValueError("typed explanation required")
    kind = raw.get("kind")
    if kind == "ARCHITECT":
        if (type(raw.get("uncertainty")) is not dict
                or type(raw.get("alternatives")) is not list
                or len(raw["alternatives"]) > 8
                or any(type(item) is not dict
                       for item in raw["alternatives"])):
            raise ValueError("invalid explanation structure")
        from_data = render_architect_explanation({
            "schema": "eai.architect.preview.v1",
            "problem_sha256": raw.get("problem_sha256"),
            "status": raw.get("status"),
            "truth_status": raw.get("truth_status"),
            "execution": "NOT_EXECUTED", "model": "LOCAL_CPU_ONLY",
            "analysis": {
                "unknowns": ["REDACTED"] * _bounded_count(
                    raw.get("uncertainty", {}).get("unknown_count"), 32),
                "contradictions": ["REDACTED"] * _bounded_count(
                    raw.get("uncertainty", {}).get("contradiction_count"), 32),
            },
            "evidence_review_required": raw.get(
                "uncertainty", {}).get("evidence_review_required"),
            "advisory_plans": [{
                "alternative_id": p.get("alternative_id"),
                "status": p.get("status"),
                "node_hashes": p.get("source_sha256"),
                "plan_steps": [{"operator": x} for x in p.get("operator_ids", [])],
            } for p in raw.get("alternatives", [])],
        })
        if from_data != raw:
            raise ValueError("tampered architect explanation")
        uncertain = raw["uncertainty"]
        lines = [
            "EAI ARCHITECT - UNVERIFIED ADVISORY",
            "STATUS: " + raw["status"],
            "TRUTH: " + raw["truth_status"],
            "PROBLEM SHA256: " + raw["problem_sha256"],
            "UNKNOWN COUNT: " + str(uncertain["unknown_count"]),
            "CONTRADICTION COUNT: " + str(uncertain["contradiction_count"]),
            "EVIDENCE REVIEW REQUIRED: " + str(
                uncertain["evidence_review_required"]).upper(),
            "ADVISORY ALTERNATIVES: " + str(len(raw["alternatives"])),
        ]
        for p in raw["alternatives"]:
            lines.append("ALTERNATIVE: " + p["alternative_id"])
            lines.append("STEP COUNT: " + str(p["step_count"]))
            lines.append("SOURCE SHA256: " + ",".join(p["source_sha256"]))
    elif kind == "PLAYER":
        if (type(raw.get("status")) is not str
                or raw["status"] not in _PLAYER_STATUS
                or raw.get("verified_real_world") is not False
                or raw.get("network") != "DISABLED_BY_DESIGN"
                or raw.get("execution") != (
                    "DENIED" if raw["status"] == "HOLD_POLICY_DENIED"
                    else "PURE_SYNTHETIC_NOOP_ONLY")):
            raise ValueError("untrusted player explanation")
        lines = [
            "EAI PLAYER - SYNTHETIC OR DENIED",
            "STATUS: " + raw["status"],
            "PROBLEM SHA256: " + _hash(raw.get("problem_sha256")),
            "PLAN SHA256: " + _hash(raw.get("plan_sha256")),
            "STEPS: " + str(_bounded_count(raw.get("interpreted_steps"))),
        ]
        if raw.get("trace_sha256") is not None:
            lines.append("TRACE SHA256: " + _hash(raw["trace_sha256"]))
    else:
        raise ValueError("unrecognized EAI explanation kind")
    lines.append("REAL-WORLD VERIFICATION: NOT ESTABLISHED")
    lines.append("EXTERNAL ACTIONS: DISABLED")
    return "\n".join(lines) + "\n"


# EAI-SWU-033: final result digest-only presentation with research separated.
def render_final_decision_trace(result) -> dict:
    """Allowlisted source SHA, counts and reason codes only; no private goal."""
    from .contracts import FinalResultSpec
    if type(result) is not FinalResultSpec:
        raise ValueError("typed final EAI result required")
    trusted = FinalResultSpec.validate(result.as_dict())
    if trusted != result:
        raise ValueError("forged final EAI result")
    if result.status == "ABSTAINED" and result.selected_alternative is not None:
        raise ValueError("abstention may not select an action")
    return {
        "schema": "eai.architect.final_trace.v1",
        "problem_sha256": _hash(result.problem_sha256),
        "status": result.status,
        "selected_alternative": result.selected_alternative,
        "source_sha256": list(result.advisory_evidence_sha256),
        "reason_codes": list(result.reason_codes),
        "evidence_count": len(result.advisory_evidence_sha256),
        "execution": "NOT_EXECUTED",
        "independent_verification": "NOT_ESTABLISHED",
        "research_lane": "OPTIONAL_OFF_SEPARATE_UNTRUSTED",
        "external_actions": 0,
        "original_writes": 0,
        "grants_real_authority": False,
    }


# EAI-SWU-042: local decision -> allowlisted no-private-payload CPU answer.
def render_local_decision_explanation(raw: dict) -> dict:
    """Validate the exact output contract before any CLI display."""
    if (type(raw) is not dict or set(raw) != {
            "schema", "problem_sha256", "status", "selected_alternative_id",
            "selected_plan_sha256", "reason_codes", "compared_alternatives",
            "unknown_count", "source_receipt_sha256", "origin",
            "external_actions", "original_writes", "provider_calls",
            "independent_verification", "real_execution_authorized",
            "active_promotion_authorized", "resource_postflight"}
            or raw["schema"] != "eai.offline.decision.v1"
            or raw["status"] not in (
                "ADVISORY_CPU_SELECTION_UNVERIFIED", "ABSTAINED",
                "HOLD_LOCAL_RESOURCE_BUDGET", "CANCELLED")
            or raw["origin"] != "LOCAL_CPU_ADVISORY_UNVERIFIED"
            or raw["independent_verification"] != "NOT_ESTABLISHED"
            or raw["external_actions"] != 0
            or raw["original_writes"] != 0
            or raw["provider_calls"] != 0
            or raw["real_execution_authorized"] is not False
            or raw["active_promotion_authorized"] is not False
            or raw["resource_postflight"] not in (
                "PROCESS_RSS_PASS_NOT_EXECUTION_AUTHORITY","HOLD")):
        raise ValueError("untrusted CPU final decision envelope")
    digest = _hash(raw["problem_sha256"])
    receipt = _hash(raw["source_receipt_sha256"])
    choices = raw["compared_alternatives"]
    if (type(choices) is not list or len(choices) > 8
            or any(type(v) is not str or not _ID.fullmatch(v)
                   for v in choices) or len(set(choices)) != len(choices)):
        raise ValueError("invalid alternative identifiers")
    selected = raw["selected_alternative_id"]
    selected_sha = raw["selected_plan_sha256"]
    eligible = raw["status"] == "ADVISORY_CPU_SELECTION_UNVERIFIED"
    if (eligible != (selected is not None)
            or eligible != (selected_sha is not None)
            or (eligible and (
                type(selected) is not str or selected not in choices
                or len(choices) < 2
                or raw["resource_postflight"] !=
                "PROCESS_RSS_PASS_NOT_EXECUTION_AUTHORITY"))
            or (selected_sha is not None
                and _hash(selected_sha) != selected_sha)):
        raise ValueError("selection does not match local decision safety state")
    reasons = raw["reason_codes"]
    if (type(reasons) is not list or not 1 <= len(reasons) <= 32
            or len(set(reasons)) != len(reasons)
            or any(type(x) is not str
                   or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", x)
                   for x in reasons)):
        raise ValueError("invalid decision reason codes")
    unknowns = _bounded_count(raw["unknown_count"], 32)
    return {
        "schema":"eai.local.cpu.answer.v1",
        "status":raw["status"],
        "problem_sha256":digest,
        "source_receipt_sha256":receipt,
        "selected_alternative_id":selected,
        "selected_plan_sha256":selected_sha,
        "compared_alternatives":list(choices),
        "reason_codes":list(reasons),
        "unknown_count":unknowns,
        "execution":"NOT_EXECUTED",
        "verification":"INDEPENDENT_ORACLE_NOT_ESTABLISHED",
        "network":"DISABLED_BY_DESIGN",
        "external_actions":0,
        "active_promotion":False,
    }


def render_local_decision_text(result: dict) -> str:
    """ASCII terminal answer contains hashes and public identifiers only."""
    if (type(result) is not dict
            or result.get("schema") != "eai.local.cpu.answer.v1"):
        raise ValueError("typed EAI CPU answer required")
    # Reconstruct only from already allowlisted output. No private goal text.
    status = result["status"]
    if status not in (
            "ADVISORY_CPU_SELECTION_UNVERIFIED", "ABSTAINED",
            "HOLD_LOCAL_RESOURCE_BUDGET", "CANCELLED"):
        raise ValueError("unsupported local CPU decision status")
    _hash(result["problem_sha256"])
    _hash(result["source_receipt_sha256"])
    selected = result.get("selected_alternative_id")
    if (selected is not None and (
            type(selected) is not str or not _ID.fullmatch(selected))):
        raise ValueError("untrusted selected alternative")
    reasons = result.get("reason_codes")
    if (type(reasons) is not list or len(reasons) > 32 or
            any(type(reason) is not str or
                not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", reason)
                for reason in reasons)):
        raise ValueError("untrusted CPU reason codes")
    if (result.get("execution") != "NOT_EXECUTED"
            or result.get("network") != "DISABLED_BY_DESIGN"
            or result.get("external_actions") != 0
            or result.get("active_promotion") is not False):
        raise ValueError("privileged CPU answer rejected")
    return "\n".join([
        "EAI LOCAL CPU DECISION - UNVERIFIED",
        "STATUS: " + status,
        "PROBLEM SHA256: " + result["problem_sha256"],
        "RECEIPT SHA256: " + result["source_receipt_sha256"],
        "SELECTED: " + (result["selected_alternative_id"] or "NONE"),
        "REASONS: " + ",".join(result["reason_codes"]),
        "VERIFIED: NOT ESTABLISHED",
        "EXTERNAL ACTIONS: DISABLED",
    ])
