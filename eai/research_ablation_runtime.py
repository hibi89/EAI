"""Paired OFF versus local fake ON result. Never calls a live provider."""
from __future__ import annotations

from dataclasses import dataclass

from .dual_mode_ablation import preview_mock_ablation
from .hydrogen_packet import ResearchPacket
from .research_mock_transport import MockApprovalReceipt, MockResearchTransport
from .research_providers import ResearchCoordinator


@dataclass(frozen=True)
class LocalPairedOutcome:
    status: str
    off_mode_status: str
    mock_mode_status: str
    request_sha256: str
    off_baseline_preserved: bool
    quarantined_ideas: int
    measured_uplift: str = "NOT_MEASURED"
    real_provider_called: bool = False
    permits_execution: bool = False
    permits_training: bool = False
    permits_promotion: bool = False


def run_local_paired_ablation(
    packet: ResearchPacket, baseline: object,
    coordinator: ResearchCoordinator, transport: MockResearchTransport, *,
    approval: MockApprovalReceipt | None = None,
    fixture_http_status: int = 200,
    now: float | None = None
) -> LocalPairedOutcome:
    """Immutable OFF CPU baseline first; compare only optional fake suggestions."""
    if (type(packet) is not ResearchPacket
            or type(coordinator) is not ResearchCoordinator
            or type(transport) is not MockResearchTransport
            or transport.coordinator is not coordinator):
        raise ValueError("explicit same-coordinator local mock research required")
    off = coordinator.evaluate(baseline)
    if off.baseline is not baseline or off.candidates:
        raise ValueError("research coordinator replaced local CPU baseline")
    mock = transport.dispatch(
        packet, approval, baseline, fixture_http_status=fixture_http_status,
        now=now)
    preview = preview_mock_ablation(packet, baseline, mock)
    if mock.baseline is not baseline or not preview.off_baseline_preserved:
        raise ValueError("fake provider attempted baseline replacement")
    return LocalPairedOutcome(
        preview.status, off.mode_status, mock.status,
        preview.request_sha256, True, preview.mock_candidate_count)
