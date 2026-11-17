"""C32 offline fake idea provenance and no auto-promotion regression."""
from dataclasses import replace
import socket
import unittest
from unittest.mock import patch

from eai.hydrogen_packet import ResearchPacket
from eai.research_mock_transport import (
    MockApprovalReceipt, MockResearchTransport, MockProposal)
from eai.research_policy import ResearchMode, ResearchPolicy
from eai.research_providers import ResearchCoordinator
from eai.research_candidates import quarantine_mock_research


class ResearchCandidateQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.packet = ResearchPacket.validate({
            "version": 1, "nonce": "candidatefake1234",
            "task_family": "synthetic.csv",
            "visibility": "PUBLIC_SYNTHETIC_ONLY",
            "abstract": "Synthetic key discrepancy test",
            "strategy_ids": ["data.test"], "objectives": ["detect.counterexample"],
        })
        self.coordinator = ResearchCoordinator(
            ResearchPolicy(mode=ResearchMode.RESEARCH_OPT_IN))
        self.transport = MockResearchTransport(self.coordinator)

    def outcome(self):
        receipt = MockApprovalReceipt.synthetic_fixture(
            self.packet, self.coordinator)
        return self.transport.dispatch(self.packet, receipt, "offline", now=100)

    def test_fake_outcome_kept_quarantined_without_network(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            receipt = quarantine_mock_research(self.packet, self.outcome())
        self.assertEqual(receipt.disposition, "QUARANTINED_LOCAL_FAKE_IDEA_ONLY")
        self.assertEqual(len(receipt.ideas), 1)
        self.assertFalse(receipt.permits_execution)
        self.assertFalse(receipt.permits_learning)
        self.assertFalse(receipt.permits_promotion)
        self.assertFalse(receipt.ideas[0].can_promote)

    def test_same_mock_outcome_deterministically_hashed(self):
        result = self.outcome()
        first = quarantine_mock_research(self.packet, result)
        second = quarantine_mock_research(self.packet, result)
        self.assertEqual(first, second)
        self.assertEqual(len(first.ideas[0].idea_sha256), 64)

    def test_fake_human_authorized_source_is_rejected(self):
        result = self.outcome()
        fake = replace(result.candidates[0], source="HUMAN_APPROVED")
        rejected = quarantine_mock_research(
            self.packet, replace(result, candidates=(fake,)))
        self.assertEqual(rejected.disposition, "HOLD_UNTRUSTED_FAKE_RESEARCH")
        self.assertEqual(rejected.ideas, ())

    def test_cross_packet_receipt_cannot_be_reused(self):
        result = replace(self.outcome(), request_sha256="0" * 64)
        decision = quarantine_mock_research(self.packet, result)
        self.assertIn("CROSS_PACKET_MOCK_OUTPUT", decision.reason_codes)
        self.assertEqual(decision.ideas, ())

    def test_fake_proposal_claiming_verified_trust_is_rejected(self):
        result = self.outcome()
        fake = replace(result.candidates[0], trust="VERIFIED")
        decision = quarantine_mock_research(
            self.packet, replace(result, candidates=(fake,)))
        self.assertIn("UNTRUSTED_MODEL_CANDIDATE", decision.reason_codes)

    def test_unknown_or_multiple_fake_candidates_rejected(self):
        result = self.outcome()
        fake = MockProposal("LOCAL_SYNTHETIC_FIXTURE",
                            "unsafe.shell.exec", self.packet.task_family)
        for changed in (
            replace(result, candidates=(fake,)),
            replace(result, candidates=(result.candidates[0], fake)),
        ):
            with self.subTest(changed=changed):
                decision = quarantine_mock_research(self.packet, changed)
                self.assertEqual(decision.ideas, ())
                self.assertFalse(decision.permits_execution)

    def test_malformed_mock_candidate_inventory_fails_closed(self):
        result = self.outcome()
        for inventory in (None, 42, "LOCAL_FAKE_UNVERIFIED"):
            with self.subTest(inventory=inventory):
                decision = quarantine_mock_research(
                    self.packet, replace(result, candidates=inventory))
                self.assertEqual(decision.ideas, ())
                self.assertIn("UNTRUSTED_CANDIDATE_COUNT", decision.reason_codes)

    def test_off_mode_has_no_candidate_ideas(self):
        off = MockResearchTransport(ResearchCoordinator())
        outcome = off.dispatch(self.packet, None, "offline")
        decision = quarantine_mock_research(self.packet, outcome)
        self.assertEqual(decision.ideas, ())
        self.assertEqual(decision.disposition, "HOLD_UNTRUSTED_FAKE_RESEARCH")

    def test_forged_packet_private_content_never_admitted(self):
        forged = replace(self.packet, abstract="private password=EXAMPLE")
        with self.assertRaises(ValueError):
            quarantine_mock_research(forged, self.outcome())
