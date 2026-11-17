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


# EAI-SWU-040: local mock result -> generation-checked OFF fallback only.
@dataclass(frozen=True)
class LocalResearchFallback:
    baseline: Any
    status: str
    reason: str
    source_generation: int
    active_generation: int
    research_candidates: tuple = ()
    provider_calls: int = 0
    paid_requests: int = 0
    external_bytes_sent: int = 0
    auto_promotion_allowed: bool = False


def settle_local_mock_research(
    coordinator: ResearchCoordinator, baseline: Any, mock_outcome,
    *, issued_generation: int, quota=None, now: float | None = None
) -> LocalResearchFallback:
    """Stale or failed *local fake* research cannot modify the CPU result.

    Mock data are not real provider replies and may not be converted into
    permission to access Hydrogen. A result is always an OFF CPU baseline.
    """
    from .research_mock_transport import MockOutcome
    from .research_quota import ResearchQuota, pause_local_mock_after_failure
    if (type(coordinator) is not ResearchCoordinator or
            type(mock_outcome) is not MockOutcome or
            mock_outcome.baseline is not baseline or
            type(issued_generation) is not int or issued_generation < 0 or
            (quota is not None and type(quota) is not ResearchQuota)):
        raise ValueError("typed local mock response and coordinator required")
    if (mock_outcome.status not in {
            "OFF", "PAUSED_POLICY", "PAUSED_MOCK_APPROVAL", "DENIED_REPLAY",
            "MOCK_PROVIDER_UNAVAILABLE", "PAUSED_QUOTA_429",
            "LATE_RESPONSE_IGNORED", "MOCK_UNVERIFIED_ONLY",
            "LOCAL_REQUEST_LIMIT", "LOCAL_TOKEN_LIMIT", "INVALID_TOKEN_BUDGET",
            "PAUSED_QUOTA"}):
        raise ValueError("unrecognized local mock status")
    stale = issued_generation != coordinator.generation
    disabled = coordinator.policy.mode is ResearchMode.OFF
    state = "OFF_LOCAL_RESEARCH_UNAVAILABLE"
    reason = "LOCAL_FAKE_IS_NOT_EXTERNAL_PROVIDER"
    if stale or mock_outcome.status == "LATE_RESPONSE_IGNORED":
        state = "OFF_IGNORED_LATE_MOCK"
        reason = "GENERATION_CHANGED_BEFORE_SETTLEMENT"
    elif mock_outcome.status == "PAUSED_QUOTA_429":
        if quota is not None:
            pause_local_mock_after_failure(quota, 429, now=now)
        coordinator.disable()
        state = "OFF_AFTER_MOCK_QUOTA_429"
        reason = "NO_PAID_FALLBACK_OR_RETRY"
    elif mock_outcome.status == "MOCK_PROVIDER_UNAVAILABLE":
        if quota is not None:
            pause_local_mock_after_failure(quota, 503, now=now)
        coordinator.disable()
        state = "OFF_AFTER_MOCK_FAILURE"
        reason = "NO_PAID_FALLBACK_OR_RETRY"
    elif disabled:
        state = "OFF"
        reason = "RESEARCH_DEFAULT_OFF"
    # Even a successful fixture never authorizes external output.
    return LocalResearchFallback(
        baseline, state, reason,
        issued_generation, coordinator.generation)
