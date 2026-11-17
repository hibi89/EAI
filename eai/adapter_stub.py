"""C22 EAI-owned opt-in adapter handshake with a permanently OFF executor.

This is a schema and policy review only. It does not import, connect to, or
change My Local AI, HAE, LA, subprocesses, sockets or third-party services.
An owner-provided hash is untrusted metadata, never actual consent.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .contracts import PlanSpec, ProblemSpec, canonical_bytes, strict_json
from .policy_gate import evaluate_plan_policy

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[a-zA-Z0-9_-]{8,40}\Z")
_ADAPTERS = frozenset({"my_local_ai", "hae", "la"})
_SCOPE = "CAPABILITY_PREVIEW_ONLY"
_MAX_BYTES = 2048


@dataclass(frozen=True)
class AdapterHandshake:
    adapter: str
    nonce: str
    problem_sha256: str
    plan_sha256: str
    requested_scope: str
    claimed_consent_sha256: str | None = None
    version: int = 1

    @classmethod
    def validate(cls, raw: dict) -> "AdapterHandshake":
        if type(raw) is not dict or set(raw) != {
            "version", "adapter", "nonce", "problem_sha256",
            "plan_sha256", "requested_scope", "claimed_consent_sha256"
        }:
            raise ValueError("unexpected adapter handshake fields")
        if type(raw["version"]) is not int or raw["version"] != 1:
            raise ValueError("unknown adapter handshake version")
        if (type(raw["adapter"]) is not str
                or raw["adapter"] not in _ADAPTERS
                or type(raw["nonce"]) is not str
                or not _NONCE.fullmatch(raw["nonce"])
                or type(raw["requested_scope"]) is not str
                or raw["requested_scope"] != _SCOPE):
            raise ValueError("unapproved adapter or scope")
        if any(type(raw[k]) is not str or not _HASH.fullmatch(raw[k])
               for k in ("problem_sha256", "plan_sha256")):
            raise ValueError("unbound adapter handshake")
        consent = raw["claimed_consent_sha256"]
        if consent is not None and (
                type(consent) is not str or not _HASH.fullmatch(consent)):
            raise ValueError("invalid untrusted consent metadata")
        if len(canonical_bytes(raw)) > _MAX_BYTES:
            raise ValueError("oversized adapter handshake")
        return cls(raw["adapter"], raw["nonce"], raw["problem_sha256"],
                   raw["plan_sha256"], raw["requested_scope"], consent)

    @classmethod
    def from_json(cls, source: str | bytes) -> "AdapterHandshake":
        return cls.validate(strict_json(source, max_bytes=_MAX_BYTES))

    def digest(self) -> str:
        """Rebuild the strict schema to reject manually forged dataclasses."""
        raw = {
            "version": self.version, "adapter": self.adapter,
            "nonce": self.nonce, "problem_sha256": self.problem_sha256,
            "plan_sha256": self.plan_sha256,
            "requested_scope": self.requested_scope,
            "claimed_consent_sha256": self.claimed_consent_sha256,
        }
        if type(self) is not AdapterHandshake or AdapterHandshake.validate(raw) != self:
            raise ValueError("untrusted adapter handshake")
        return hashlib.sha256(canonical_bytes(raw)).hexdigest()


@dataclass(frozen=True)
class AdapterHandshakeReview:
    status: str
    adapter: str
    handshake_sha256: str
    problem_sha256: str
    plan_sha256: str
    reason_codes: tuple[str, ...]
    network_bytes_sent: int = 0
    handler_invoked: bool = False
    can_execute: bool = False
    grants_consent: bool = False


def inspect_adapter_handshake(
    problem: ProblemSpec, plan: PlanSpec, handshake: AdapterHandshake
) -> AdapterHandshakeReview:
    if type(handshake) is not AdapterHandshake:
        raise ValueError("explicit typed handshake required")
    digest = handshake.digest()
    policy = evaluate_plan_policy(problem, plan)
    reasons = ["ADAPTER_EXECUTOR_DISABLED_BY_DEFAULT",
               "NO_INDEPENDENT_OWNER_CONSENT"]
    if (handshake.problem_sha256 != policy.problem_sha256
            or handshake.plan_sha256 != policy.plan_sha256):
        reasons.append("CROSS_TASK_HANDSHAKE_DENIED")
    if policy.disposition != "PURE_SYNTHETIC_PREVIEW_ONLY":
        reasons.append("PLAN_POLICY_DENIED")
    if handshake.claimed_consent_sha256 is not None:
        reasons.append("CLAIMED_CONSENT_HASH_IS_NOT_AUTHORITY")
    status = ("STUB_CONTRACT_MATCHED_EXECUTOR_DISABLED" if
              len(reasons) == 2 else "HOLD_UNTRUSTED_ADAPTER_HANDSHAKE")
    return AdapterHandshakeReview(status, handshake.adapter, digest,
                                  policy.problem_sha256, policy.plan_sha256,
                                  tuple(sorted(reasons)))


# EAI-SWU-031: convenience bridge to an always-OFF local port registry.
def inspect_disabled_adapter_port(
    problem: ProblemSpec, plan: PlanSpec, handshake: AdapterHandshake,
):
    from .adapter_registry import DisabledAdapterRegistry
    return DisabledAdapterRegistry().inspect(problem, plan, handshake)
