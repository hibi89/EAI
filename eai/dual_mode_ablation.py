"""C33 paired OFF vs local fake-ON ablation envelope (no efficacy claims).

The EAI OFF baseline is immutable-by-contract and is never replaced by a model
suggestion. Local MOCK candidates remain quarantined, not real Hydrogen.
"""
from __future__ import annotations

from dataclasses import dataclass

from .hydrogen_packet import ResearchPacket
from .research_mock_transport import MockOutcome
from .research_candidates import quarantine_mock_research


@dataclass(frozen=True)
class MockAblationPreview:
    status: str
    request_sha256: str
    off_baseline_preserved: bool
    mock_candidate_count: int
    measured_accuracy_delta: str = "NOT_MEASURED"
    measured_cost_delta: str = "NOT_MEASURED"
    real_provider_called: bool = False
    verified_improvement: bool = False
    permits_training: bool = False
    permits_action: bool = False


def preview_mock_ablation(
    packet: ResearchPacket, off_baseline: object, on: MockOutcome
) -> MockAblationPreview:
    if type(packet) is not ResearchPacket or type(on) is not MockOutcome:
        raise ValueError("typed synthetic packet and mock outcome required")
    checked = ResearchPacket.from_json(packet.to_json_bytes())
    receipt = quarantine_mock_research(checked, on)
    same_off = on.baseline is off_baseline
    if not same_off:
        disposition = "HOLD_DIFFERENT_OFF_BASELINE"
    elif on.status == "OFF":
        disposition = "OFF_ONLY_NO_MOCK_CANDIDATES"
    elif receipt.disposition != "QUARANTINED_LOCAL_FAKE_IDEA_ONLY":
        disposition = "HOLD_UNTRUSTED_MOCK_ABLATION"
    else:
        disposition = "PAIRED_LOCAL_MOCK_PREVIEW_UNVERIFIED"
    return MockAblationPreview(
        disposition, checked.request_sha256(), same_off,
        len(receipt.ideas) if same_off else 0)


def compare_local_off_mock(packet: ResearchPacket, baseline: object,
                           coordinator, transport, *, approval=None,
                           fixture_http_status: int = 200,
                           now: float | None = None):
    """Offline-only caller joining the coordinator, fake transport and quarantine."""
    from .research_ablation_runtime import run_local_paired_ablation
    return run_local_paired_ablation(
        packet, baseline, coordinator, transport, approval=approval,
        fixture_http_status=fixture_http_status, now=now)
