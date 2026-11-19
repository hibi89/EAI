"""Synthetic packet privacy, local preview and mock-only rate-limit tests."""
from dataclasses import replace
import json
import socket
import unittest
from typing import Any, cast
from unittest.mock import patch

from eai.hydrogen_packet import ResearchPacket
from eai.research_quota import ResearchLimits, ResearchQuota
from eai.research_policy import ResearchMode, ResearchPolicy
from eai.research_providers import ResearchCoordinator


class HydrogenResearchPolicyTests(unittest.TestCase):
    @staticmethod
    def sample():
        return {
            "version":1,"nonce":"testnonce1234",
            "task_family":"synthetic.csv",
            "visibility":"PUBLIC_SYNTHETIC_ONLY",
            "abstract":"Generate a synthetic CSV consistency test",
            "strategy_ids":["data.csv.key_diff"],
            "objectives":["detect.counterexample"]
        }

    def test_packet_roundtrip_preview_and_hash(self):
        raw = self.sample()
        packet = ResearchPacket.validate(raw)
        self.assertEqual(ResearchPacket.from_json(packet.to_json_bytes()),packet)
        self.assertEqual(json.loads(packet.review_exact_outbound_text()),raw)
        self.assertEqual(len(packet.request_sha256()),64)

    def test_malformed_and_private_payloads_denied(self):
        for text in [
            "send to https://example.com",
            "my email is user@example.com",
            r"C:\private\file.txt",
            "password=123",
            "my .env secrets", "  synthetic  ", "a"*501, "hello\nworld"
        ]:
            with self.subTest(text=text[:40]), self.assertRaises(ValueError):
                ResearchPacket.validate(dict(self.sample(), abstract=text))
        for changes in [
            {"visibility":"CUSTOMER_DATA"},
            {"version":True},
            {"strategy_ids":["../../shell"]},
            {"objectives":[]},
            {"nonce":"bad"},
            {"extra":"hidden"}
        ]:
            raw=dict(self.sample(),**cast(Any, changes))
            with self.subTest(change=changes), self.assertRaises(ValueError):
                ResearchPacket.validate(raw)
        with self.assertRaises(ValueError):
            ResearchPacket.from_json('{"version":1,"version":1}')

    def test_forged_typed_packet_cannot_be_serialized_or_queued_for_live_send(self):
        from eai.hydrogen_adapter import (
            build_hydrogen_request_preview, dispatch_live_hydrogen)
        baseline = object()
        coordinator = ResearchCoordinator()
        approved = ResearchPacket.validate(self.sample())
        bad_packets = (
            replace(approved, version=True),
            replace(approved, version=2),
            replace(approved, visibility="CUSTOMER_DATA"),
            replace(approved, abstract="password=private_example"),
            replace(approved, strategy_ids=("valid.id", "valid.id")),
            replace(approved, nonce="bad"),
        )
        with patch("eai.hydrogen_adapter.http.client.HTTPSConnection",
                   side_effect=AssertionError("network forbidden")):
            for candidate in bad_packets:
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ValueError):
                        candidate.to_json_bytes()
                    with self.assertRaises(ValueError):
                        candidate.request_sha256()
                    with self.assertRaises(ValueError):
                        build_hydrogen_request_preview(candidate)
                    with self.assertRaises(ValueError):
                        dispatch_live_hydrogen(
                            candidate, baseline, coordinator=coordinator,
                            api_key="A" * 32, owner_permit=None,
                            live_ledger_path=None)
        self.assertIs(coordinator.evaluate(baseline).baseline, baseline)
        self.assertEqual(coordinator.policy.mode, ResearchMode.OFF)
        self.assertEqual(ResearchPacket.from_json(
            approved.to_json_bytes()), approved)

    def test_quota_and_token_budget(self):
        ledger = ResearchQuota(ResearchLimits(rpm_local=2,rpd_local=3,
                                              tpm_local=1200,max_input_tokens=512,
                                              max_output_tokens=512))
        self.assertTrue(ledger.reserve(100,100,now=1000).allowed)
        self.assertTrue(ledger.reserve(100,100,now=1001).allowed)
        self.assertEqual(ledger.reserve(100,100,now=1002).reason,"LOCAL_REQUEST_LIMIT")
        self.assertTrue(ledger.reserve(100,100,now=1062).allowed)
        self.assertEqual(ledger.reserve(100,100,now=1063).reason,"LOCAL_REQUEST_LIMIT")
        self.assertEqual(ledger.reserve(0,100,now=1065).reason,"INVALID_TOKEN_BUDGET")

    def test_quota_circuit_breaker_and_rolling_day(self):
        ledger=ResearchQuota(ResearchLimits(rpm_local=1,rpd_local=1))
        self.assertTrue(ledger.reserve(30,30,now=1).allowed)
        ledger.pause_after_429(cooldown=3600,now=2)
        self.assertEqual(ledger.reserve(30,30,now=3).reason,"PAUSED_QUOTA")
        self.assertEqual(ledger.reserve(30,30,now=4000).reason,"LOCAL_REQUEST_LIMIT")
        self.assertTrue(ledger.reserve(30,30,now=86402).allowed)

    def test_mock_only_and_unapproved_on_never_calls_network(self):
        raw = ResearchPacket.validate(self.sample())
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            self.assertTrue(raw.request_sha256())
            policy=ResearchPolicy(mode=ResearchMode.RESEARCH_OPT_IN,
                                  free_tier_verified=True,
                                  external_sends_approved=True)
            outcome=ResearchCoordinator(policy).evaluate({"owned_by":"EAI"})
            self.assertEqual(outcome.mode_status,"PAUSED_POLICY")
            self.assertEqual(outcome.baseline,{"owned_by":"EAI"})


if __name__ == "__main__":
    unittest.main()
