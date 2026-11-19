"""P2-06 synthetic-only scoped Player, replay, compensation and adapter isolation.

No real tool, original write, external provider or owner approval is exercised.
"""
from dataclasses import replace
import socket
import unittest
from unittest.mock import patch

from eai.contracts import ProblemSpec, PlanSpec
from eai.policy_gate import evaluate_plan_policy, plan_digest
from eai.player_runtime import (
    execute_pure_synthetic_preview, audit_pure_player_trace,
)
from eai.player_executor import dispatch_isolated_pure_player
from eai.player_observation import observe_and_compensate_pure_port
from eai.adapter_registry import DisabledAdapterRegistry
from eai.adapter_stub import AdapterHandshake


class PlayerScopeP2Tests(unittest.TestCase):
    def setUp(self):
        self.problem = ProblemSpec.validate({
            "version": 1, "id": "synthetic.port.scope",
            "goal": "private synthetic review", "domain": "research",
            "state_refs": [], "assumptions": [],
            "hard_constraints": ["must:local_only"], "objectives": ["safety"],
            "oracle": "synthetic.only", "permissions": ["pure"],
            "budget": {"max_steps": 8, "max_seconds": 30}, "risk": "LOW",
        })
        self.plan = PlanSpec.validate({
            "version": 1, "problem_sha256": self.problem.digest(),
            "steps": [
                {"id": "step_a", "operator": "synthetic.noop.v1",
                 "requires": [], "capability": "pure"},
                {"id": "step_x", "operator": "synthetic.noop.v1",
                 "requires": [], "capability": "pure"},
                {"id": "step_b", "operator": "synthetic.noop.v1",
                 "requires": ["step_a"], "capability": "pure"},
                {"id": "step_y", "operator": "synthetic.noop.v1",
                 "requires": ["step_x"], "capability": "pure"},
            ], "budget": {"max_steps": 4, "max_seconds": 20},
        })

    def invoke(self, step="step_b", **kw):
        return dispatch_isolated_pure_player(
            self.problem, self.plan, requested_step=step,
            interpret_synthetic=True, **kw)

    def test_scoped_receipts_exclude_unrelated_and_descendant_steps(self):
        with patch.object(socket, "socket",
                          side_effect=AssertionError("network disabled")):
            a = self.invoke()
            b = self.invoke()
        self.assertEqual(a, b)
        self.assertEqual(a.observed_steps, ("step_a", "step_b"))
        self.assertEqual(self.invoke("step_a").observed_steps, ("step_a",))
        self.assertEqual(self.invoke("step_y").observed_steps, ("step_x", "step_y"))
        self.assertEqual(a.plan_sha256, plan_digest(self.plan))
        self.assertEqual(a.real_tool_calls, 0)
        self.assertEqual(a.original_writes, 0)
        self.assertEqual(a.network_calls, 0)
        self.assertFalse(a.authorized_active_promotion)

    def test_scoped_trace_hash_binds_requested_step_and_replay(self):
        policy = evaluate_plan_policy(self.problem, self.plan)
        scoped = execute_pure_synthetic_preview(
            self.problem, self.plan, policy, requested_step="step_b")
        full = execute_pure_synthetic_preview(self.problem, self.plan, policy)
        first = execute_pure_synthetic_preview(
            self.problem, self.plan, policy, requested_step="step_a")
        self.assertEqual(tuple(r.step_id for r in scoped.step_receipts),
                         ("step_a", "step_b"))
        self.assertNotEqual(scoped.trace_sha256, full.trace_sha256)
        self.assertNotEqual(scoped.trace_sha256, first.trace_sha256)
        self.assertEqual(audit_pure_player_trace(
            self.problem, self.plan, policy, scoped,
            requested_step="step_b").status,
            "PURE_TRACE_REPLAY_MATCH_UNVERIFIED")
        self.assertEqual(audit_pure_player_trace(
            self.problem, self.plan, policy, scoped).status,
            "REJECTED_UNREPRODUCIBLE_PURE_TRACE")

    def test_scoped_cancel_stops_before_selected_step_not_other_branch(self):
        cancelled = self.invoke(cancel_before_step="step_b")
        self.assertEqual(cancelled.status,
                         "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED")
        self.assertEqual(cancelled.observed_steps, ("step_a",))
        self.assertNotEqual(cancelled.trace_sha256, self.invoke().trace_sha256)
        self.assertEqual(self.invoke(cancel_before_step="step_a").observed_steps, ())
        with self.assertRaisesRegex(ValueError, "selected pure scope"):
            self.invoke(cancel_before_step="step_x")
        with self.assertRaisesRegex(ValueError, "selected pure scope"):
            self.invoke("step_a", cancel_before_step="step_b")
        with self.assertRaises(ValueError):
            self.invoke("nonexistent")

    def test_opt_in_evidence_policy_and_forged_privilege_hold(self):
        no_consent = dispatch_isolated_pure_player(
            self.problem, self.plan, requested_step="step_b")
        self.assertEqual(no_consent.status,
                         "HOLD_EXPLICIT_SYNTHETIC_INTERPRETATION_REQUIRED")
        self.assertIsNone(no_consent.trace_sha256)
        denied = self.invoke(architect_truth="CONFLICT")
        self.assertEqual(denied.status, "HOLD_SCOPED_PLAYER_PORT")
        receipt = self.invoke()
        with self.assertRaises(PermissionError):
            observe_and_compensate_pure_port(
                self.problem, self.plan,
                replace(receipt, real_tool_calls=1), request_compensation=True)
        self.assertFalse(receipt.semantic_verification)

    def test_compensation_is_idempotent_noop_and_change_replay_is_denied(self):
        original = self.invoke()
        one = observe_and_compensate_pure_port(
            self.problem, self.plan, original, request_compensation=True)
        two = observe_and_compensate_pure_port(
            self.problem, self.plan, original, request_compensation=True)
        self.assertEqual(one, two)
        self.assertEqual(one.status, "PURE_IN_MEMORY_INTENT_COMPENSATED_NOT_REAL_ROLLBACK")
        self.assertTrue(one.idempotent)
        self.assertFalse(one.compensating_action_executed)
        self.assertFalse(one.original_files_modified)
        self.assertFalse(one.rollback_of_real_action_proven)
        self.assertEqual(observe_and_compensate_pure_port(
            self.problem, self.plan, original).status,
            "HOLD_EXPLICIT_COMPENSATION_REQUEST_REQUIRED")
        forged = replace(original, observed_steps=("step_a", "step_x", "step_b"))
        self.assertEqual(observe_and_compensate_pure_port(
            self.problem, self.plan, forged,
            request_compensation=True).status, "HOLD_UNREPRODUCIBLE_PURE_TRACE")
        changed = PlanSpec.validate({
            "version": 1, "problem_sha256": self.problem.digest(),
            "steps": [
                {"id": "step_a", "operator": "synthetic.noop.v1",
                 "requires": [], "capability": "pure"},
            ], "budget": {"max_steps": 1, "max_seconds": 20},
        })
        self.assertEqual(observe_and_compensate_pure_port(
            self.problem, changed, original, request_compensation=True).status,
            "HOLD_UNREPRODUCIBLE_PURE_TRACE")
        cancelled = self.invoke(cancel_before_step="step_b")
        result = observe_and_compensate_pure_port(
            self.problem, self.plan, cancelled, request_compensation=True,
            cancel_before_step="step_b")
        self.assertEqual(result.status, "PURE_IN_MEMORY_INTENT_COMPENSATED_NOT_REAL_ROLLBACK")
        self.assertEqual(observe_and_compensate_pure_port(
            self.problem, self.plan, cancelled, request_compensation=True).status,
            "HOLD_UNREPRODUCIBLE_PURE_TRACE")

    def test_cross_repo_adapters_remain_off_without_real_calls(self):
        ports = DisabledAdapterRegistry()
        self.assertEqual({p.adapter for p in ports.ports()},
                         {"my_local_ai", "hae", "la"})
        for target in ("my_local_ai", "hae", "la"):
            with self.subTest(target=target):
                hand = AdapterHandshake.validate({
                    "version": 1, "adapter": target, "nonce": "p2scope1234",
                    "problem_sha256": self.problem.digest(),
                    "plan_sha256": plan_digest(self.plan),
                    "requested_scope": "CAPABILITY_PREVIEW_ONLY",
                    "claimed_consent_sha256": None,
                })
                with patch.object(socket, "socket",
                                  side_effect=AssertionError("network disabled")):
                    audit = ports.inspect(self.problem, self.plan, hand)
                self.assertEqual(audit.status, "DISABLED_PORT_MATCHED_UNCONNECTED")
                self.assertEqual(audit.port.state, "OFF")
                self.assertFalse(audit.can_execute)
                self.assertFalse(audit.handler_invoked)
                self.assertFalse(audit.can_authorize)
                self.assertEqual(audit.network_bytes_sent, 0)


if __name__ == "__main__":
    unittest.main()
