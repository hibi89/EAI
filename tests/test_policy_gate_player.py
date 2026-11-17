"""Pure Player C20/C21 approval, typed DAG and fail-closed security tests."""
from dataclasses import replace
from unittest.mock import patch
import socket
import unittest

from eai.contracts import PlanSpec, ProblemSpec
from eai.policy_gate import evaluate_plan_policy, plan_digest
from eai.player_runtime import execute_pure_synthetic_preview


class PolicyGatePlayerTests(unittest.TestCase):
    @staticmethod
    def problem(**overrides):
        raw = {
            "version": 1, "id": "synthetic.player",
            "goal": "PRIVATE do not reveal", "domain": "research",
            "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["safety"],
            "oracle": "synthetic.only", "permissions": ["pure"],
            "budget": {"max_steps": 4, "max_seconds": 30},
            "risk": "LOW",
        }
        raw.update(overrides)
        return ProblemSpec.validate(raw)

    @staticmethod
    def plan(problem, *, operator="synthetic.noop.v1", capability="pure"):
        return PlanSpec.validate({
            "version": 1, "problem_sha256": problem.digest(),
            "steps": [
                {"id": "step01", "operator": operator,
                 "requires": [], "capability": capability},
                {"id": "step02", "operator": "synthetic.noop.v1",
                 "requires": ["step01"], "capability": "pure"},
            ], "budget": {"max_steps": 3, "max_seconds": 20},
        })

    def test_two_step_real_interpreter_is_deterministic_without_io(self):
        p = self.problem()
        plan = self.plan(p)
        policy = evaluate_plan_policy(p, plan)
        self.assertEqual(policy.disposition, "PURE_SYNTHETIC_PREVIEW_ONLY")
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            receipt = execute_pure_synthetic_preview(p, plan, policy)
            duplicate = execute_pure_synthetic_preview(p, plan, policy)
        self.assertEqual(receipt, duplicate)
        self.assertEqual(len(receipt.step_receipts), 2)
        self.assertEqual(receipt.step_receipts[1].dependency_sha256,
                         (receipt.step_receipts[0].step_sha256,))
        self.assertEqual(receipt.external_actions, 0)
        self.assertEqual(receipt.original_writes, 0)
        self.assertFalse(receipt.promotion_authorized)
        self.assertFalse(receipt.real_world_verified)

    def test_cancel_before_second_step_has_bounded_prefix(self):
        p = self.problem()
        plan = self.plan(p)
        policy = evaluate_plan_policy(p, plan)
        partial = execute_pure_synthetic_preview(
            p, plan, policy, cancel_before_step="step02")
        self.assertEqual(partial.status, "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED")
        self.assertEqual(len(partial.step_receipts), 1)
        self.assertNotEqual(partial.trace_sha256,
                            execute_pure_synthetic_preview(p, plan, policy).trace_sha256)

    def test_stale_cross_problem_plan_cannot_execute(self):
        p = self.problem()
        other = self.problem(goal="different")
        plan = self.plan(p)
        policy = evaluate_plan_policy(other, plan)
        self.assertEqual(policy.disposition, "HOLD_POLICY_DENIED")
        self.assertIn("CROSS_PROBLEM_PLAN", policy.reason_codes)
        with self.assertRaises(PermissionError):
            execute_pure_synthetic_preview(other, plan, policy)

    def test_csv_read_operator_denied_even_with_local_read_permission(self):
        p = self.problem(permissions=["pure", "local.read"])
        plan = self.plan(p, operator="csv.reconcile.v1",
                         capability="local.read")
        policy = evaluate_plan_policy(p, plan)
        self.assertIn("REAL_OR_UNSUPPORTED_OPERATOR_BLOCKED", policy.reason_codes)
        with self.assertRaises(PermissionError):
            execute_pure_synthetic_preview(p, plan, policy)

    def test_model_supplied_approval_digest_grants_nothing(self):
        p = self.problem()
        plan = self.plan(p)
        policy = evaluate_plan_policy(
            p, plan, proposed_approval_hash="f" * 64)
        self.assertEqual(policy.disposition, "HOLD_POLICY_DENIED")
        with self.assertRaises(PermissionError):
            execute_pure_synthetic_preview(p, plan, policy)

    def test_forged_approval_and_policy_dataclass_are_rejected(self):
        p = self.problem()
        plan = self.plan(p)
        allowed = evaluate_plan_policy(p, plan)
        forged = replace(allowed, grants_real_authority=True)
        with self.assertRaises(PermissionError):
            execute_pure_synthetic_preview(p, plan, forged)

    def test_unvalidated_plan_dataclass_cannot_inject_shell_operator(self):
        p = self.problem()
        clean = self.plan(p)
        forged = replace(clean, steps=(
            ("step01", "shell.exec.v1", (), "pure"),
        ))
        with self.assertRaises(ValueError):
            evaluate_plan_policy(p, forged)

    def test_pure_plan_hash_is_pinned(self):
        p = self.problem()
        plan = self.plan(p)
        self.assertEqual(plan_digest(plan), plan_digest(plan))
        other = replace(plan, steps=plan.steps[:1])
        self.assertNotEqual(plan_digest(plan), plan_digest(other))


if __name__ == "__main__":
    unittest.main()
