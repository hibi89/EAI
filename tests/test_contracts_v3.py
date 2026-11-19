"""Synthetic-only strict contract tests for independent EAI V3 cognition."""
import copy
import json
import unittest
from typing import cast

from eai.contracts import (
    CognitiveResult, DesignSpec, PlanSpec, ProblemSpec,
    canonical_sha256, strict_json
)


class ContractV3Tests(unittest.TestCase):
    def problem(self):
        return {
            "version": 1, "id": "synthetic.analysis", "goal": "Compare fixtures",
            "domain": "data", "state_refs": ["fixture.a"],
            "assumptions": ["No private records"],
            "hard_constraints": ["Read-only"], "objectives": ["Correct result"],
            "oracle": "fixture.compare", "permissions": ["local.read"],
            "budget": {"max_steps": 5, "max_seconds": 60}, "risk": "LOW"
        }

    def test_problem_canonical_hash_and_no_legacy_mutation(self):
        raw = self.problem()
        p = ProblemSpec.validate(raw)
        self.assertEqual(len(p.digest()), 64)
        self.assertEqual(ProblemSpec.validate(dict(reversed(list(raw.items())))).digest(), p.digest())
        self.assertEqual(raw, self.problem())
        from eai.intent import IntentSpec
        from eai.cognition import ResultSpec
        self.assertEqual(IntentSpec.validate({
            "version": 1, "task": "calculate", "expression": "2+2", "query": ""
        }).task, "calculate")
        self.assertEqual(ResultSpec("OK", "calculate").status, "OK")

    def test_reject_unknown_fields_permissions_and_invalid_budget(self):
        for bad in [
            dict(self.problem(), exec="shell"),
            dict(self.problem(), version=True),
            dict(self.problem(), permissions=["github.write"]),
            dict(self.problem(), permissions=["local.read", "local.read"]),
            dict(self.problem(), risk="ADMIN"),
            dict(self.problem(), budget={"max_steps": 500, "max_seconds": 1}),
            dict(self.problem(), budget={"max_steps": True, "max_seconds": 1}),
        ]:
            with self.subTest(case=bad), self.assertRaises(ValueError):
                ProblemSpec.validate(bad)

    def test_strict_json_and_encoding(self):
        a = self.problem()
        self.assertEqual(strict_json(json.dumps(a)), a)
        for bad in [
            '{"version":1,"version":1}', '[]', '{"a":NaN}',
            b'\xff', b'x'*32769
        ]:
            with self.subTest(bad=repr(bad)[:30]), self.assertRaises(ValueError):
                strict_json(cast(str | bytes, bad))

    def test_two_options_and_blocked_design(self):
        h = ProblemSpec.validate(self.problem()).digest()
        a = {"id": "option.a", "strategy_refs": ["cpu.calculate.v1"],
             "tradeoffs": ["Fast"], "verification": "exact"}
        b = {"id": "option.b", "strategy_refs": ["cpu.compare.v1"],
             "tradeoffs": ["Alternative"], "verification": "exact"}
        raw = {"version": 1, "problem_sha256": h,
               "alternatives": [a, b], "blocked_reason": ""}
        self.assertEqual(len(DesignSpec.validate(raw).alternatives), 2)
        with self.assertRaises(ValueError):
            DesignSpec.validate(dict(raw, alternatives=[a, a]))
        self.assertEqual(len(DesignSpec.validate(
            dict(raw, alternatives=[], blocked_reason="No oracle")).alternatives), 0)
        with self.assertRaises(ValueError):
            DesignSpec.validate(dict(raw, alternatives=[]))

    def test_bounded_plan_and_cycle_or_arbitrary_operator_denied(self):
        h = ProblemSpec.validate(self.problem()).digest()
        first = {"id": "start", "operator": "synthetic.noop.v1",
                 "requires": [], "capability": "pure"}
        last = {"id": "verify", "operator": "evidence.verify_receipt.v1",
                "requires": ["start"], "capability": "pure"}
        raw = {"version": 1, "problem_sha256": h,
               "steps": [first, last], "budget": {"max_steps": 4, "max_seconds": 30}}
        self.assertEqual(len(PlanSpec.validate(raw).steps), 2)
        bads = [
            [dict(first, operator="shell.run")],
            [dict(first, capability="github.write")],
            [dict(first, requires=["verify"]), last],
            [first, dict(last, requires=["missing"])],
            [first, first],
        ]
        for steps in bads:
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                PlanSpec.validate(dict(raw, steps=steps))

    def test_independent_result_never_trusts_claim_as_proof(self):
        h = ProblemSpec.validate(self.problem()).digest()
        raw = {"version": 1, "status": "UNVERIFIED", "problem_sha256": h,
               "evidence_sha256": [], "unknowns": ["No oracle"]}
        self.assertEqual(CognitiveResult.validate(raw).status, "UNVERIFIED")
        for bad in [
            dict(raw, status="APPROVED_FOR_EXECUTION"),
            dict(raw, evidence_sha256=["not-a-sha"]),
            dict(raw, unknowns=[""])]:
            with self.assertRaises(ValueError):
                CognitiveResult.validate(bad)

    def test_hash_is_integrity_only(self):
        h1 = canonical_sha256(self.problem())
        bad = copy.deepcopy(self.problem())
        bad["goal"] = "Different fixture"
        self.assertNotEqual(h1, canonical_sha256(bad))


if __name__ == "__main__":
    unittest.main()
