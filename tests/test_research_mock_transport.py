"""No-network mock receipt and fail-closed fallback regression."""
import socket
import unittest
from unittest.mock import patch

from eai.hydrogen_packet import ResearchPacket
from eai.research_mock_transport import (
    MockApprovalReceipt, MockResearchTransport,
)
from eai.research_policy import ResearchMode, ResearchPolicy
from eai.research_providers import ResearchCoordinator
from eai.research_quota import ResearchLimits, ResearchQuota


class MockResearchTransportTests(unittest.TestCase):
    @staticmethod
    def packet():
        return ResearchPacket.validate({
            "version": 1, "nonce": "syntheticnonce1234",
            "task_family": "synthetic.csv", "visibility": "PUBLIC_SYNTHETIC_ONLY",
            "abstract": "Synthetic CSV consistency test with fake inputs",
            "strategy_ids": ["data.csv.key_diff"],
            "objectives": ["detect.counterexample"],
        })

    @staticmethod
    def on():
        # Not an external transfer approval; local mock remains offline.
        return ResearchCoordinator(ResearchPolicy(mode=ResearchMode.RESEARCH_OPT_IN))

    def test_off_bypasses_fake_transport_without_network(self):
        coordinator = ResearchCoordinator()
        transport = MockResearchTransport(coordinator)
        baseline = {"design": "offline"}
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            result = transport.dispatch(self.packet(), None, baseline, now=100)
        self.assertEqual(result.status, "OFF")
        self.assertIs(result.baseline, baseline)
        self.assertEqual(result.candidates, ())

    def test_exact_preview_receipt_only_generates_unverified_fixture(self):
        coordinator = self.on()
        packet = self.packet()
        receipt = MockApprovalReceipt.synthetic_fixture(packet, coordinator)
        transport = MockResearchTransport(coordinator)
        baseline = {"owner": "EAI"}
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            result = transport.dispatch(packet, receipt, baseline, now=100)
        self.assertEqual(result.status, "MOCK_UNVERIFIED_ONLY")
        self.assertEqual(result.candidates[0].trust, "LOCAL_FAKE_UNVERIFIED")
        self.assertEqual(result.candidates[0].source, "LOCAL_SYNTHETIC_FIXTURE")
        self.assertIs(result.baseline, baseline)
        self.assertEqual(result.quota_index, 1)
        self.assertTrue(result.approval_sha256)

    def test_forged_receipt_replay_and_cross_packet_denied(self):
        coordinator = self.on()
        transport = MockResearchTransport(coordinator)
        packet = self.packet()
        receipt = MockApprovalReceipt.synthetic_fixture(packet, coordinator)
        forged = MockApprovalReceipt(receipt.request_sha256, "f"*64,
                                     packet.nonce, receipt.generation,
                                     test_acknowledged=True)
        self.assertEqual(transport.dispatch(packet, forged, 1, now=10).status,
                         "PAUSED_MOCK_APPROVAL")
        other = ResearchPacket.validate({
            "version":1, "nonce":"differentnonce123",
            "task_family":"synthetic.csv", "visibility":"PUBLIC_SYNTHETIC_ONLY",
            "abstract":"Completely different synthetic fixture",
            "strategy_ids":[], "objectives":["detect.counterexample"],
        })
        self.assertEqual(transport.dispatch(other, receipt, 1, now=11).status,
                         "PAUSED_MOCK_APPROVAL")
        self.assertEqual(transport.dispatch(packet, receipt, 1, now=12).status,
                         "MOCK_UNVERIFIED_ONLY")
        self.assertEqual(transport.dispatch(packet, receipt, 1, now=13).status,
                         "DENIED_REPLAY")

    def test_429_cooldown_and_quota_fallback_preserve_baseline(self):
        coordinator = self.on()
        transport = MockResearchTransport(coordinator,
                     ResearchQuota(ResearchLimits(rpm_local=2,rpd_local=2)))
        packet = self.packet()
        baseline = ("trusted",)
        first = transport.dispatch(
            packet, MockApprovalReceipt.synthetic_fixture(packet, coordinator),
            baseline, fixture_http_status=429, now=100)
        self.assertEqual(first.status, "PAUSED_QUOTA_429")
        self.assertIs(first.baseline, baseline)
        different = ResearchPacket.validate({
            "version":1, "nonce":"anothernonce5555",
            "task_family":"synthetic.math", "visibility":"PUBLIC_SYNTHETIC_ONLY",
            "abstract":"Synthetic arithmetic check",
            "strategy_ids":[], "objectives":["detect.counterexample"],
        })
        paused = transport.dispatch(
            different, MockApprovalReceipt.synthetic_fixture(different, coordinator),
            baseline, now=101)
        self.assertEqual(paused.status, "PAUSED_QUOTA")
        self.assertEqual(paused.candidates, ())

    def test_disable_invalidates_old_receipt_and_never_activates_remote(self):
        coordinator = self.on()
        packet = self.packet()
        receipt = MockApprovalReceipt.synthetic_fixture(packet, coordinator)
        transport = MockResearchTransport(coordinator)
        coordinator.disable()
        self.assertEqual(transport.dispatch(packet, receipt, "base").status, "OFF")
        coordinator.policy = ResearchPolicy(mode=ResearchMode.RESEARCH_OPT_IN)
        self.assertEqual(transport.dispatch(packet, receipt, "base").status,
                         "PAUSED_MOCK_APPROVAL")
        self.assertEqual(coordinator.evaluate("base").mode_status, "PAUSED_POLICY")

    def test_directly_forged_packet_denied_prior_to_mock_quota(self):
        packet = ResearchPacket("testnonce1234", "synthetic.csv",
                                "private password=ABCD", (), ("detect.counterexample",))
        coordinator = self.on()
        transport = MockResearchTransport(coordinator)
        with self.assertRaises(ValueError):
            transport.dispatch(packet, None, "base")
        self.assertEqual(transport.quota.reserve(30, 30, now=5).request_index, 1)


if __name__ == "__main__":
    unittest.main()
