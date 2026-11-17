"""Optional research provider boundary. OFF never imports an SDK or contacts a host.

This is the OFF-only implementation skeleton for EAI-V3-11. No Hydrogen
adapter, network client, key handling, model result trust or API usage exists.
"""
from dataclasses import dataclass
from typing import Any

from .research_policy import ResearchMode, ResearchPolicy


class NullProvider:
    """Always available without credentials, Internet or installed dependencies."""

    def propose(self, _packet: object = None) -> tuple:
        return ()


@dataclass(frozen=True)
class ResearchOutcome:
    baseline: Any
    candidates: tuple
    mode_status: str
    reason: str = ""


class ResearchCoordinator:
    def __init__(self, policy: ResearchPolicy | None = None):
        self.policy = policy if policy is not None else ResearchPolicy()
        if type(self.policy) is not ResearchPolicy:
            raise ValueError("invalid EAI research policy")
        self._null = NullProvider()
        self._generation = 0

    def disable(self) -> None:
        """Synchronous cancel/invalidate marker; future adapters must honor it."""
        self.policy = ResearchPolicy()
        self._generation += 1

    def evaluate(self, baseline: Any) -> ResearchOutcome:
        """Return the exact independent baseline; never load cloud dependencies."""
        if self.policy.mode is ResearchMode.OFF:
            return ResearchOutcome(baseline, self._null.propose(), "OFF")
        # Even when flags look permissive, adapter and per-request safe packet,
        # explicit preview, project quota and independent verifier DO NOT YET EXIST.
        # Until they are implemented a remote call is impossible.
        return ResearchOutcome(baseline, (), "PAUSED_POLICY",
                               "Live provider remains unimplemented and unapproved")

    @property
    def generation(self) -> int:
        return self._generation
