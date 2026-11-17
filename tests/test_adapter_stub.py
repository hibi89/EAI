"""C22 contract-only adapter tests: no external process or cross-repo imports."""
from dataclasses import replace
import json
import socket
import unittest
from unittest.mock import patch

from eai.adapter_stub import AdapterHandshake, inspect_adapter_handshake
from eai.contracts import ProblemSpec, PlanSpec
from eai.policy_gate import plan_digest


class AdapterStubTests(unittest.TestCase):
    def setUp(self):
        self.problem = ProblemSpec.validate({
            "version": 1, "id": "synthetic.adapter",
            "goal": "PRIVATE never send", "domain": "research",
            "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["safety"],
            "oracle": "synthetic", "permissions": ["pure"],
            "budget": {"max_steps": 2, "max_seconds": 20},
            "risk": "LOW",
        })
        self.plan = PlanSpec.validate({
            "version": 1, "problem_sha256": self.problem.digest(),
            "steps": [{"id": "step01", "operator": "synthetic.noop.v1",
                       "requires": [], "capability": "pure"}],
            "budget": {"max_steps": 1, "max_seconds": 10},
        })
        self.raw = {
            "version": 1, "adapter": "my_local_ai",
            "nonce": "synthetic12345", "problem_sha256": self.problem.digest(),
            "plan_sha256": plan_digest(self.plan),
            "requested_scope": "CAPABILITY_PREVIEW_ONLY",
            "claimed_consent_sha256": None,
        }

    def test_stub_only_handshake_never_calls_external(self):
        handshake = AdapterHandshake.from_json(json.dumps(self.raw))
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            review = inspect_adapter_handshake(self.problem, self.plan, handshake)
        self.assertEqual(review.status, "STUB_CONTRACT_MATCHED_EXECUTOR_DISABLED")
        self.assertFalse(review.handler_invoked)
        self.assertEqual(review.network_bytes_sent, 0)
        self.assertFalse(review.can_execute)
        self.assertFalse(review.grants_consent)

    def test_all_three_explicit_adapter_targets_remain_off(self):
        for target in ("my_local_ai", "hae", "la"):
            with self.subTest(target=target):
                self.raw["adapter"] = target
                hand = AdapterHandshake.validate(self.raw)
                self.assertFalse(inspect_adapter_handshake(
                    self.problem, self.plan, hand).can_execute)

    def test_other_service_or_privileged_scope_denied(self):
        for key, value in (("adapter", "os.shell"),
                           ("requested_scope", "EXECUTE_TOOLS")):
            with self.subTest(key=key):
                tampered = dict(self.raw)
                tampered[key] = value
                with self.assertRaises(ValueError):
                    AdapterHandshake.validate(tampered)

    def test_unknown_and_duplicate_json_keys_denied(self):
        raw = dict(self.raw)
        raw["token"] = "PRIVATE"
        with self.assertRaises(ValueError):
            AdapterHandshake.validate(raw)
        duplicate = json.dumps(self.raw).replace(
            '"version": 1', '"version": 1, "version": 1', 1)
        with self.assertRaises(ValueError):
            AdapterHandshake.from_json(duplicate)

    def test_stale_plan_hash_and_claimed_consent_do_not_authorize(self):
        self.raw["plan_sha256"] = "a" * 64
        self.raw["claimed_consent_sha256"] = "b" * 64
        review = inspect_adapter_handshake(
            self.problem, self.plan, AdapterHandshake.validate(self.raw))
        self.assertIn("CROSS_TASK_HANDSHAKE_DENIED", review.reason_codes)
        self.assertIn("CLAIMED_CONSENT_HASH_IS_NOT_AUTHORITY",
                      review.reason_codes)
        self.assertFalse(review.can_execute)

    def test_forged_typed_handshake_does_not_bypass_validation(self):
        hand = AdapterHandshake.validate(self.raw)
        with self.assertRaises(ValueError):
            inspect_adapter_handshake(
                self.problem, self.plan, replace(hand, requested_scope="WRITE"))

    def test_wrong_risk_policy_never_invokes_adapter(self):
        from dataclasses import replace as change
        bad = change(self.problem, risk="HIGH")
        hand = AdapterHandshake.validate(self.raw)
        review = inspect_adapter_handshake(bad, self.plan, hand)
        self.assertIn("PLAN_POLICY_DENIED", review.reason_codes)
        self.assertFalse(review.handler_invoked)
