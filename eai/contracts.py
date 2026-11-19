"""EAI V3 typed, bounded cognitive contracts. No execution or model imports.

These research contracts are additive: the legacy eai.intent.IntentSpec and
eai.cognition.ResultSpec retain their existing v1 runtime semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

MAX_DOCUMENT_BYTES = 32 * 1024
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_PERMISSIONS = frozenset({"pure", "local.read"})
_ALLOWED_OPERATORS = frozenset({
    "synthetic.noop.v1", "csv.reconcile.v1", "evidence.verify_receipt.v1"
})


def _reject_duplicate(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError("nonfinite JSON number is forbidden")


def strict_json(data: str | bytes, *, max_bytes: int = MAX_DOCUMENT_BYTES) -> dict:
    """Parse untrusted JSON with byte and duplicate-key limits, no side effects."""
    if type(data) is bytes:
        if len(data) > max_bytes:
            raise ValueError("document byte limit exceeded")
        try:
            data = data.decode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid UTF-8") from exc
    if type(data) is not str or len(data.encode("utf-8")) > max_bytes:
        raise ValueError("invalid document type or size")
    try:
        raw = json.loads(data, object_pairs_hook=_reject_duplicate,
                         parse_constant=_reject_constant)
    except (json.JSONDecodeError, RecursionError, UnicodeError) as exc:
        raise ValueError("invalid or too deeply nested JSON") from exc
    if type(raw) is not dict:
        raise ValueError("top-level JSON object required")
    return raw


def canonical_bytes(raw: dict) -> bytes:
    """Stable serialization for typed, already-validated documents only."""
    if type(raw) is not dict:
        raise ValueError("canonical document must be an object")
    try:
        return json.dumps(raw, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("non-canonical document") from exc


def canonical_sha256(raw: dict) -> str:
    return hashlib.sha256(canonical_bytes(raw)).hexdigest()


def _keys(raw: dict, required: set[str]) -> None:
    if type(raw) is not dict or set(raw) != required:
        raise ValueError("unexpected contract fields")


def _name(value: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("invalid contract identifier")
    return value


def _text(value: str, limit: int = 1024) -> str:
    if (type(value) is not str or not 1 <= len(value) <= limit
            or "\x00" in value):
        raise ValueError("invalid contract text")
    return value


def _names(raw: list, limit: int = 32) -> tuple[str, ...]:
    if type(raw) is not list or len(raw) > limit:
        raise ValueError("invalid contract name list")
    values = tuple(_name(item) for item in raw)
    if len(set(values)) != len(values):
        raise ValueError("duplicate contract name")
    return values


def _texts(raw: list, limit: int = 32) -> tuple[str, ...]:
    if type(raw) is not list or len(raw) > limit:
        raise ValueError("invalid contract text list")
    return tuple(_text(item, 256) for item in raw)


def _version(raw: dict) -> None:
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise ValueError("unsupported contract version")


def _hash(value: str) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise ValueError("invalid SHA256 reference")
    return value


def _budget(raw: dict) -> tuple[int, int]:
    _keys(raw, {"max_steps", "max_seconds"})
    steps, seconds = raw["max_steps"], raw["max_seconds"]
    if (type(steps) is not int or not 1 <= steps <= 64 or
            type(seconds) is not int or not 1 <= seconds <= 300):
        raise ValueError("invalid bounded resource budget")
    return steps, seconds


@dataclass(frozen=True)
class ProblemSpec:
    """EAI-owned problem, no provider or executable text authority."""
    id: str
    goal: str
    domain: str
    state_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    hard_constraints: tuple[str, ...]
    objectives: tuple[str, ...]
    oracle: str
    permissions: tuple[str, ...]
    budget: tuple[int, int]
    risk: str
    version: int = 1

    @classmethod
    def validate(cls, raw: dict) -> "ProblemSpec":
        _keys(raw, {"version", "id", "goal", "domain", "state_refs",
                    "assumptions", "hard_constraints", "objectives", "oracle",
                    "permissions", "budget", "risk"})
        _version(raw)
        permissions = _names(raw["permissions"], 4)
        if not set(permissions) <= _ALLOWED_PERMISSIONS:
            raise ValueError("privileged problem permission denied")
        risk = raw["risk"]
        if risk not in ("LOW", "MEDIUM", "HIGH") or type(risk) is not str:
            raise ValueError("unknown problem risk")
        return cls(_name(raw["id"]), _text(raw["goal"], 2000),
                   _name(raw["domain"]), _names(raw["state_refs"]),
                   _texts(raw["assumptions"]), _texts(raw["hard_constraints"]),
                   _texts(raw["objectives"]), _text(raw["oracle"], 256),
                   permissions, _budget(raw["budget"]), risk)

    def digest(self) -> str:
        return canonical_sha256({
            "version": 1, "id": self.id, "goal": self.goal, "domain": self.domain,
            "state_refs": list(self.state_refs), "assumptions": list(self.assumptions),
            "hard_constraints": list(self.hard_constraints),
            "objectives": list(self.objectives), "oracle": self.oracle,
            "permissions": list(self.permissions),
            "budget": {"max_steps": self.budget[0], "max_seconds": self.budget[1]},
            "risk": self.risk
        })


@dataclass(frozen=True)
class DesignSpec:
    """Alternative plans with explicit evidence obligations, never executes."""
    problem_sha256: str
    alternatives: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str], ...]
    blocked_reason: str
    version: int = 1

    @classmethod
    def validate(cls, raw: dict) -> "DesignSpec":
        _keys(raw, {"version", "problem_sha256", "alternatives", "blocked_reason"})
        _version(raw)
        alternatives = raw["alternatives"]
        if type(alternatives) is not list or len(alternatives) > 8:
            raise ValueError("invalid design alternatives")
        parsed = []
        for option in alternatives:
            _keys(option, {"id", "strategy_refs", "tradeoffs", "verification"})
            parsed.append((_name(option["id"]), _names(option["strategy_refs"]),
                           _texts(option["tradeoffs"]), _text(option["verification"], 256)))
        if len({opt[0] for opt in parsed}) != len(parsed):
            raise ValueError("duplicate design alternative")
        reason = raw["blocked_reason"]
        if type(reason) is not str or len(reason) > 256:
            raise ValueError("invalid blocked reason")
        if not parsed and not reason.strip():
            raise ValueError("design requires alternatives or blocked reason")
        return cls(_hash(raw["problem_sha256"]), tuple(parsed), reason)


@dataclass(frozen=True)
class PlanSpec:
    """Read-only bounded, dependency-ordered typed plan. Not executable itself."""
    problem_sha256: str
    steps: tuple[tuple[str, str, tuple[str, ...], str], ...]
    budget: tuple[int, int]
    version: int = 1

    @classmethod
    def validate(cls, raw: dict) -> "PlanSpec":
        _keys(raw, {"version", "problem_sha256", "steps", "budget"})
        _version(raw)
        limit = _budget(raw["budget"])
        steps = raw["steps"]
        if type(steps) is not list or not 1 <= len(steps) <= limit[0]:
            raise ValueError("invalid bounded plan steps")
        parsed = []
        earlier: set[str] = set()
        for step in steps:
            _keys(step, {"id", "operator", "requires", "capability"})
            sid = _name(step["id"])
            op = _name(step["operator"])
            deps = _names(step["requires"])
            capability = step["capability"]
            if (sid in earlier or not set(deps) <= earlier or
                    op not in _ALLOWED_OPERATORS or
                    type(capability) is not str or
                    capability not in _ALLOWED_PERMISSIONS):
                raise ValueError("unsafe/cyclic/unknown plan operation")
            earlier.add(sid)
            parsed.append((sid, op, deps, capability))
        return cls(_hash(raw["problem_sha256"]), tuple(parsed), limit)


@dataclass(frozen=True)
class CognitiveResult:
    """Independent EAI evidence status, not a generative model answer."""
    status: str
    problem_sha256: str
    evidence_sha256: tuple[str, ...]
    unknowns: tuple[str, ...]
    version: int = 1

    @classmethod
    def validate(cls, raw: dict) -> "CognitiveResult":
        _keys(raw, {"version", "status", "problem_sha256",
                    "evidence_sha256", "unknowns"})
        _version(raw)
        status = raw["status"]
        if type(status) is not str or status not in {
                "VERIFIED", "CONFLICT", "UNVERIFIED", "UNSUPPORTED"}:
            raise ValueError("unsupported result status")
        evidence = raw["evidence_sha256"]
        if type(evidence) is not list or len(evidence) > 32:
            raise ValueError("invalid evidence references")
        refs = tuple(_hash(v) for v in evidence)
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate evidence reference")
        return cls(status, _hash(raw["problem_sha256"]), refs,
                   _texts(raw["unknowns"]))


# EAI P1 SWU 002: final, non-authorizing architect output.
@dataclass(frozen=True)
class FinalResultSpec:
    problem_sha256: str
    status: str
    selected_alternative: str | None
    advisory_evidence_sha256: tuple[str, ...]
    reason_codes: tuple[str, ...]
    execution: str = "NOT_EXECUTED"
    version: int = 1

    @classmethod
    def validate(cls, raw: dict) -> "FinalResultSpec":
        _keys(raw, {"version", "problem_sha256", "status",
                    "selected_alternative", "advisory_evidence_sha256",
                    "reason_codes", "execution"})
        _version(raw)
        status = raw["status"]
        if type(status) is not str or status not in ("ADVISORY_ONLY", "ABSTAINED"):
            raise ValueError("final architect status cannot assert verification")
        chosen = raw["selected_alternative"]
        if chosen is not None:
            chosen = _name(chosen)
        if (status == "ADVISORY_ONLY") != (chosen is not None):
            raise ValueError("final alternative/status mismatch")
        evidence = raw["advisory_evidence_sha256"]
        if type(evidence) is not list or len(evidence) > 32:
            raise ValueError("invalid final evidence references")
        refs = tuple(_hash(v) for v in evidence)
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate final evidence reference")
        reasons = raw["reason_codes"]
        if (type(reasons) is not list or len(reasons) > 32 or
                any(type(x) is not str or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", x)
                    for x in reasons) or len(set(reasons)) != len(reasons)):
            raise ValueError("invalid final reason codes")
        if raw["execution"] != "NOT_EXECUTED":
            raise ValueError("architect result cannot claim an execution")
        return cls(_hash(raw["problem_sha256"]), status, chosen,
                   refs, tuple(reasons))

    def as_dict(self) -> dict:
        return {
            "version": 1, "problem_sha256": self.problem_sha256,
            "status": self.status, "selected_alternative": self.selected_alternative,
            "advisory_evidence_sha256": list(self.advisory_evidence_sha256),
            "reason_codes": list(self.reason_codes), "execution": "NOT_EXECUTED",
        }
