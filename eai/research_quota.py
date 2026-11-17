"""Local *mock-only* research quota & circuit-breaker, not an API entitlement.

These limits are deliberately conservative local caps, NOT Google's RPM/TPM/
RPD limits. Real API access requires further proof, approval and durable
cross-process project-level accounting, currently NOT implemented.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class ResearchLimits:
    rpm_local: int = 2
    rpd_local: int = 5
    tpm_local: int = 2048
    max_input_tokens: int = 512
    max_output_tokens: int = 512

    def __post_init__(self):
        values = (
            self.rpm_local,self.rpd_local,self.tpm_local,
            self.max_input_tokens,self.max_output_tokens
        )
        if any(type(v) is not int or v < 1 for v in values):
            raise ValueError("quota limits must be positive integers")
        if (self.rpm_local > 60 or self.rpd_local > 100 or
                self.tpm_local > 32768 or self.max_input_tokens > 2048 or
                self.max_output_tokens > 2048):
            raise ValueError("local quota ceiling exceeds safety cap")


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    request_index: int = 0


class ResearchQuota:
    """In-memory strict accounting for fake transport; no paid/live readiness."""

    def __init__(self, limits: ResearchLimits | None = None):
        self.limits = limits if limits is not None else ResearchLimits()
        if type(self.limits) is not ResearchLimits:
            raise ValueError("invalid research quota")
        self._requests = deque()
        self._lock = Lock()
        self._pause_until = 0.0
        self._count = 0

    def pause_after_429(self, cooldown: int = 3600, *, now: float | None = None) -> None:
        if type(cooldown) is not int or not 1 <= cooldown <= 86400:
            raise ValueError("invalid cooldown")
        stamp = monotonic() if now is None else float(now)
        with self._lock:
            self._pause_until = max(self._pause_until, stamp + cooldown)

    def reserve(self, input_tokens: int, output_cap_tokens: int, *,
                now: float | None = None) -> QuotaDecision:
        if (type(input_tokens) is not int or type(output_cap_tokens) is not int
                or not 1 <= input_tokens <= self.limits.max_input_tokens
                or not 1 <= output_cap_tokens <= self.limits.max_output_tokens):
            return QuotaDecision(False, "INVALID_TOKEN_BUDGET")
        stamp = monotonic() if now is None else float(now)
        if stamp < 0:
            return QuotaDecision(False, "INVALID_TIME")
        with self._lock:
            if stamp < self._pause_until:
                return QuotaDecision(False, "PAUSED_QUOTA")
            # Rolling 24h window is stricter than assuming a free-tier reset.
            while self._requests and stamp - self._requests[0][0] >= 86400:
                self._requests.popleft()
            recent = [(t, reserved) for t, reserved in self._requests
                      if 0 <= stamp - t < 60]
            if (len(self._requests) >= self.limits.rpd_local or
                    len(recent) >= self.limits.rpm_local):
                return QuotaDecision(False, "LOCAL_REQUEST_LIMIT")
            if sum(tokens for _, tokens in recent) + input_tokens + output_cap_tokens > self.limits.tpm_local:
                return QuotaDecision(False, "LOCAL_TOKEN_LIMIT")
            self._count += 1
            self._requests.append((stamp, input_tokens + output_cap_tokens))
            return QuotaDecision(True, "LOCAL_RESERVED_MOCK_ONLY", self._count)


# EAI-SWU-036: opt-in persistent local-only quota factory.
def open_durable_mock_quota(path, *, limits: ResearchLimits | None = None,
                            allow_create: bool = False):
    """Use a fresh isolated SQLite ledger, never expose real API permission."""
    from .research_quota_store import DurableMockQuota
    return DurableMockQuota(path, limits=limits, allow_create=allow_create)
