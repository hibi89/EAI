"""Strictly LOCAL fake Hydrogen transport and synthetic approval receipts.

There is no client, URL, socket, SDK or live external sender in this module.
A mock receipt is deliberately NOT proof of a human-approved real transfer.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .hydrogen_packet import ResearchPacket
from .research_policy import ResearchMode
from .research_providers import ResearchCoordinator
from .research_quota import ResearchQuota

_MOCK_SCOPE = "LOCAL_SYNTHETIC_TEST_ONLY"
_SAFE_HTTP_FIXTURES = frozenset({200, 403, 429, 503})


@dataclass(frozen=True)
class MockApprovalReceipt:
    request_sha256: str
    preview_sha256: str
    nonce: str
    generation: int
    scope: str = _MOCK_SCOPE
    test_acknowledged: bool = False

    @classmethod
    def synthetic_fixture(cls, packet: ResearchPacket,
                          coordinator: ResearchCoordinator) -> "MockApprovalReceipt":
        """Synthetic test artifact only; can NEVER authorize a remote API call."""
        checked = ResearchPacket.from_json(packet.to_json_bytes())
        preview = checked.review_exact_outbound_text().encode("utf-8")
        return cls(checked.request_sha256(), hashlib.sha256(preview).hexdigest(),
                   checked.nonce, coordinator.generation, test_acknowledged=True)


@dataclass(frozen=True)
class MockProposal:
    source: str
    idea_id: str
    task_family: str
    trust: str = "LOCAL_FAKE_UNVERIFIED"


@dataclass(frozen=True)
class MockOutcome:
    baseline: object
    candidates: tuple[MockProposal, ...]
    status: str
    request_sha256: str = ""
    approval_sha256: str = ""
    quota_index: int = 0


class MockResearchTransport:
    """A deterministically generated local fixture, never a cloud proxy."""

    def __init__(self, coordinator: ResearchCoordinator,
                 quota: ResearchQuota | None = None):
        if type(coordinator) is not ResearchCoordinator:
            raise ValueError("explicit EAI coordinator required")
        self.coordinator = coordinator
        self.quota = quota if quota is not None else ResearchQuota()
        if type(self.quota) is not ResearchQuota:
            raise ValueError("mock transport requires local quota")
        self._used = set()

    def dispatch(self, packet: ResearchPacket, approval: MockApprovalReceipt | None,
                 baseline: object, *, fixture_http_status: int = 200,
                 now: float | None = None) -> MockOutcome:
        # Reparse round-trip because direct dataclass construction bypasses
        # ResearchPacket.validate and could otherwise admit private content.
        if type(packet) is not ResearchPacket:
            raise ValueError("invalid research packet type")
        checked = ResearchPacket.from_json(packet.to_json_bytes())
        request_hash = checked.request_sha256()
        if type(fixture_http_status) is not int or fixture_http_status not in _SAFE_HTTP_FIXTURES:
            raise ValueError("unknown synthetic response fixture")
        if self.coordinator.policy.mode is ResearchMode.OFF:
            return MockOutcome(baseline, (), "OFF", request_hash)
        if (type(approval) is not MockApprovalReceipt or
                approval.scope != _MOCK_SCOPE or approval.test_acknowledged is not True or
                type(approval.generation) is not int or
                approval.generation != self.coordinator.generation or
                approval.nonce != checked.nonce or
                approval.request_sha256 != request_hash or
                approval.preview_sha256 != hashlib.sha256(
                    checked.review_exact_outbound_text().encode("utf-8")).hexdigest()):
            return MockOutcome(baseline, (), "PAUSED_MOCK_APPROVAL", request_hash)
        key = (approval.generation, request_hash, checked.nonce)
        if key in self._used:
            return MockOutcome(baseline, (), "DENIED_REPLAY", request_hash)
        # This fake receipt binds exact local preview bytes, NOT human identity,
        # account tier, permissions, billing, provider response or real approval.
        # Never forward this receipt to any real adapter.
        tokens = max(1, (len(checked.to_json_bytes()) + 3) // 4)
        decision = self.quota.reserve(tokens, 64, now=now)
        if not decision.allowed:
            return MockOutcome(baseline, (), decision.reason, request_hash)
        self._used.add(key)
        receipt_hash = hashlib.sha256(
            (approval.request_sha256 + approval.preview_sha256 +
             str(approval.generation) + approval.scope).encode("ascii")).hexdigest()
        if fixture_http_status == 429:
            self.quota.pause_after_429(now=now)
            return MockOutcome(baseline, (), "PAUSED_QUOTA_429", request_hash,
                               receipt_hash, decision.request_index)
        if fixture_http_status != 200:
            return MockOutcome(baseline, (), "MOCK_PROVIDER_UNAVAILABLE", request_hash,
                               receipt_hash, decision.request_index)
        if self.coordinator.policy.mode is ResearchMode.OFF or (
                self.coordinator.generation != approval.generation):
            return MockOutcome(baseline, (), "LATE_RESPONSE_IGNORED", request_hash,
                               receipt_hash, decision.request_index)
        proposal = MockProposal("LOCAL_SYNTHETIC_FIXTURE",
                                "synthetic.counterexample.v1", checked.task_family)
        return MockOutcome(baseline, (proposal,), "MOCK_UNVERIFIED_ONLY",
                           request_hash, receipt_hash, decision.request_index)
