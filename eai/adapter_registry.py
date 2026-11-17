"""EAI-SWU-031 fixed local port registry: all adapters are permanently OFF.

This module has NO SDK/handler loading, network, subprocess or cross-repo I/O.
The registry is metadata for human review, not a connection manager.
"""
from __future__ import annotations

from dataclasses import dataclass

from .adapter_stub import (
    AdapterHandshake, AdapterHandshakeReview, inspect_adapter_handshake)
from .contracts import PlanSpec, ProblemSpec


@dataclass(frozen=True)
class AdapterPort:
    adapter: str
    scope: str = "CAPABILITY_PREVIEW_ONLY"
    state: str = "OFF"
    external_access: bool = False
    handler_registered: bool = False


@dataclass(frozen=True)
class AdapterRegistryReview:
    adapter: str
    status: str
    handshake_review: AdapterHandshakeReview
    port: AdapterPort
    network_bytes_sent: int = 0
    handler_invoked: bool = False
    can_execute: bool = False
    can_authorize: bool = False


class DisabledAdapterRegistry:
    """Read-only fixed ports; untrusted handshake never activates anything."""

    _KNOWN = ("my_local_ai", "hae", "la")

    def ports(self) -> tuple[AdapterPort, ...]:
        return tuple(AdapterPort(adapter=name) for name in self._KNOWN)

    def inspect(
        self, problem: ProblemSpec, plan: PlanSpec,
        handshake: AdapterHandshake,
    ) -> AdapterRegistryReview:
        if type(handshake) is not AdapterHandshake:
            raise ValueError("typed adapter handshake required")
        requested = handshake.digest()  # independently strict revalidation
        review = inspect_adapter_handshake(problem, plan, handshake)
        if (review.handshake_sha256 != requested or
                review.handler_invoked or review.network_bytes_sent or
                review.can_execute or review.grants_consent):
            raise ValueError("adapter handshake tried to assume authority")
        match = [p for p in self.ports() if p.adapter == handshake.adapter]
        if len(match) != 1 or match[0].state != "OFF":
            raise ValueError("unsupported or enabled adapter port")
        return AdapterRegistryReview(
            handshake.adapter, "DISABLED_PORT_MATCHED_UNCONNECTED"
            if review.status == "STUB_CONTRACT_MATCHED_EXECUTOR_DISABLED"
            else "HOLD_UNTRUSTED_ADAPTER_REQUEST",
            review, match[0])
