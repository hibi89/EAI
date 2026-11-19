"""Research OFF must be useful without provider, Internet, API keys or cloud SDK."""
import importlib
import json
import os
import socket
import unittest
from typing import Any, cast
from unittest.mock import patch

from eai.research_policy import ResearchMode, ResearchPolicy
from eai.research_providers import NullProvider, ResearchCoordinator


class ResearchOfflineTests(unittest.TestCase):
    def test_null_provider_and_default_mode(self):
        self.assertEqual(NullProvider().propose(), ())
        engine = ResearchCoordinator()
        baseline = {"answer": "local CPU result", "trace": ["CPU"]}
        result = engine.evaluate(baseline)
        self.assertIs(result.baseline, baseline)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.mode_status, "OFF")

    def test_no_network_credentials_or_optional_import_in_off(self):
        baseline = {"value": 42}
        with patch.object(socket, "socket", side_effect=AssertionError("network opened")), \
             patch.object(os, "getenv", side_effect=AssertionError("key lookup")), \
             patch.object(importlib, "import_module",
                          side_effect=AssertionError("external module import")):
            out = ResearchCoordinator().evaluate(baseline)
        self.assertEqual(out.mode_status, "OFF")
        self.assertIs(out.baseline, baseline)

    def test_paid_policy_and_malformed_config_denied(self):
        for raw in [
            {"mode": "ON"},
            {"free_only": False},
            {"paid_budget_usd": 1},
            {"paid_budget_usd": True},
            {"external_sends_approved": 1},
            {"free_tier_verified": "yes"},
        ]:
            with self.subTest(config=raw), self.assertRaises(ValueError):
                ResearchPolicy(**cast(Any, raw))

    def test_on_without_verified_tier_or_consent_remains_offline(self):
        for approved, verified in [(False, False), (True, False), (False, True),
                                   (True, True)]:
            policy = ResearchPolicy(mode=ResearchMode.RESEARCH_OPT_IN,
                                    external_sends_approved=approved,
                                    free_tier_verified=verified)
            engine = ResearchCoordinator(policy)
            self.assertEqual(policy.allows_remote_proposal(), approved and verified)
            baseline = [1, 2, 3]
            with patch.object(socket, "socket", side_effect=AssertionError("network")):
                outcome = engine.evaluate(baseline)
            self.assertEqual(outcome.mode_status, "PAUSED_POLICY")
            self.assertIs(outcome.baseline, baseline)
            self.assertEqual(outcome.candidates, ())

    def test_detach_never_erases_baseline_or_promotes_candidates(self):
        engine = ResearchCoordinator(ResearchPolicy(mode=ResearchMode.RESEARCH_OPT_IN))
        old = engine.generation
        baseline = {"axnode_hash": "unchanged", "decision": "CPU"}
        engine.disable()
        self.assertEqual(engine.generation, old + 1)
        self.assertEqual(engine.policy.mode, ResearchMode.OFF)
        outcome = engine.evaluate(baseline)
        self.assertEqual(outcome.mode_status, "OFF")
        self.assertIs(outcome.baseline, baseline)
        self.assertNotIn("provider", json.dumps(outcome.baseline))


if __name__ == "__main__":
    unittest.main()
