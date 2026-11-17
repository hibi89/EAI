"""C33 same-baseline mock ON/OFF pairing with no remote or uplift claim."""
from dataclasses import replace
import socket
import unittest
from unittest.mock import patch

from eai.dual_mode_ablation import preview_mock_ablation
from eai.hydrogen_packet import ResearchPacket
from eai.research_mock_transport import MockApprovalReceipt, MockResearchTransport
from eai.research_policy import ResearchMode, ResearchPolicy
from eai.research_providers import ResearchCoordinator


class DualModeAblationTests(unittest.TestCase):
    def setUp(self):
        self.packet = ResearchPacket.validate({
            "version": 1, "nonce": "ablationtest2026",
            "task_family": "synthetic.csv",
            "visibility": "PUBLIC_SYNTHETIC_ONLY",
            "abstract": "Synthetic CSV invariant test",
            "strategy_ids": ["data.synthetic"], "objectives": ["detect.counterexample"],
        })
        self.off = {"status": "OFF_BASELINE_UNVERIFIED"}
        self.coordinator = ResearchCoordinator(
            ResearchPolicy(mode=ResearchMode.RESEARCH_OPT_IN))
        self.transport = MockResearchTransport(self.coordinator)

    def mock(self):
        token = MockApprovalReceipt.synthetic_fixture(
            self.packet, self.coordinator)
        return self.transport.dispatch(self.packet, token, self.off, now=100)

    def test_same_off_baseline_mock_on_is_non_authoritative(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            report = preview_mock_ablation(self.packet, self.off, self.mock())
        self.assertEqual(report.status, "PAIRED_LOCAL_MOCK_PREVIEW_UNVERIFIED")
        self.assertEqual(report.mock_candidate_count, 1)
        self.assertTrue(report.off_baseline_preserved)
        self.assertFalse(report.verified_improvement)
        self.assertFalse(report.real_provider_called)
        self.assertFalse(report.permits_action)
        self.assertFalse(report.permits_training)
        self.assertEqual(report.measured_accuracy_delta, "NOT_MEASURED")

    def test_cross_baseline_substitution_denied_even_equal_value(self):
        on = self.mock()
        changed = replace(on, baseline={"status": "OFF_BASELINE_UNVERIFIED"})
        report = preview_mock_ablation(self.packet, self.off, changed)
        self.assertEqual(report.status, "HOLD_DIFFERENT_OFF_BASELINE")
        self.assertEqual(report.mock_candidate_count, 0)

    def test_off_mode_returns_no_mock_candidates(self):
        transport = MockResearchTransport(ResearchCoordinator())
        on = transport.dispatch(self.packet, None, self.off)
        report = preview_mock_ablation(self.packet, self.off, on)
        self.assertEqual(report.status, "OFF_ONLY_NO_MOCK_CANDIDATES")
        self.assertEqual(report.mock_candidate_count, 0)

    def test_tampered_request_sha_denied(self):
        tampered = replace(self.mock(), request_sha256="0" * 64)
        report = preview_mock_ablation(self.packet, self.off, tampered)
        self.assertEqual(report.status, "HOLD_UNTRUSTED_MOCK_ABLATION")
        self.assertEqual(report.mock_candidate_count, 0)

    def test_mock_proposal_cannot_claim_promotion(self):
        on = self.mock()
        forged = replace(on.candidates[0], trust="ACTIVE")
        report = preview_mock_ablation(
            self.packet, self.off, replace(on, candidates=(forged,)))
        self.assertEqual(report.status, "HOLD_UNTRUSTED_MOCK_ABLATION")

    def test_mock_transport_failure_keeps_off_baseline(self):
        receipt = MockApprovalReceipt.synthetic_fixture(
            self.packet, self.coordinator)
        on = self.transport.dispatch(
            self.packet, receipt, self.off, fixture_http_status=503, now=100)
        report = preview_mock_ablation(self.packet, self.off, on)
        self.assertTrue(report.off_baseline_preserved)
        self.assertEqual(report.mock_candidate_count, 0)
        self.assertEqual(report.status, "HOLD_UNTRUSTED_MOCK_ABLATION")
