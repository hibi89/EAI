"""Actual existing read-only CPU baseline only on fresh synthetic test files."""
from dataclasses import replace
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.contracts import ProblemSpec
from eai.logic_oracle import SyntheticComparison
from eai.logic_synthesis import LogicSynthesizer
from eai.solver_reference_check import (
    compare_real_cpu_on_synthetic, review_candidate_with_cpu_baseline,
)


class RealCPUSyntheticReferenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = AXNodeStore(Path(temp.name) / "isolated")
        self.addCleanup(self.store.close)
        a = self.store.import_node(json.dumps(self.node("data.first", [])))
        b = self.store.import_node(json.dumps(self.node("data.second", [a])))
        self.problem = ProblemSpec.validate({
            "version": 1, "id": "synthetic.cpu.baseline",
            "goal": "PRIVATE do not release user data", "domain": "data",
            "state_refs": [], "assumptions": [], "hard_constraints": [],
            "objectives": ["correctness"], "oracle": "fixture.compare",
            "permissions": ["local.read"],
            "budget": {"max_steps": 5, "max_seconds": 60}, "risk": "LOW",
        })
        self.candidate = LogicSynthesizer(self.store).compose(
            self.problem, (a, b))

    @staticmethod
    def node(name, parents):
        return {
            "schema": "eai.axnode.v1", "id": name, "version": 1,
            "kind": "strategy", "status": "CANDIDATE",
            "signature": {
                "inputs": {"source": "csv_ref", "prior": "difference_receipt"},
                "output": "difference_receipt"},
            "pre": ["authorized_local_only"], "post": ["independent_check"],
            "steps": [{"skill": "csv.reconcile.v1"}],
            "capabilities": ["local.read"], "parent_hashes": parents,
            "tests": {"unit": [], "heldout": [], "negative": []},
            "evidence": [],
            "provenance": {"author": "eai_synthetic", "source": "local_only"},
            "budget": {"max_steps": 2, "max_seconds": 20},
        }

    @staticmethod
    def fixtures():
        return (
            SyntheticComparison(
                "family.agreement", (("a", "1.0"), ("b", "2.00")),
                (("a", "1.00"), ("b", "2")), ()),
            SyntheticComparison(
                "family.discrepancy", (("a", "1"), ("b", "2")),
                (("a", "3"), ("c", "4")), ("a", "b", "c")),
        )

    def test_real_solver_agrees_with_independent_reference_on_synthetic(self):
        with patch.object(socket, "socket",
                          side_effect=AssertionError("network used")):
            audit = review_candidate_with_cpu_baseline(
                self.store, self.problem, self.candidate, self.fixtures())
        self.assertEqual(audit.disposition,
                         "CPU_BASELINE_MATCHES_CANDIDATE_STILL_UNVERIFIED")
        self.assertTrue(audit.baseline_cpu_executed)
        self.assertFalse(audit.composed_candidate_executed)
        self.assertFalse(audit.semantic_verified)
        self.assertFalse(audit.permits_promotion)
        self.assertEqual(
            [r.verdict for r in audit.results],
            ["BASELINE_CPU_MATCH_UNVERIFIED"] * 2)
        self.assertEqual([r.actual_status for r in audit.results],
                         ["AGREE", "CONFLICT"])

    def test_forged_cpu_output_detected_instead_of_self_verifying(self):
        with patch("eai.solver_reference_check.reconcile_csv",
                   return_value={"status": "AGREE", "counts": {},
                                 "differences": [], "truncated": 0,
                                 "sources": []}):
            audit = review_candidate_with_cpu_baseline(
                self.store, self.problem, self.candidate, self.fixtures())
        self.assertEqual(audit.disposition,
                         "HOLD_CPU_BASELINE_MISMATCH_OR_INCONCLUSIVE")
        self.assertTrue(all(r.verdict == "BASELINE_CPU_MISMATCH"
                            for r in audit.results))

    def test_cpu_solver_input_mutation_is_detected_not_certified(self):
        def forged_runner(left,right,**kwargs):
            Path(left).write_bytes(b"corrupted synthetic source")
            return {"status":"AGREE","counts":{},"differences":[],
                    "truncated":0,"sources":[]}
        with patch("eai.solver_reference_check.reconcile_csv",
                   side_effect=forged_runner):
            result=compare_real_cpu_on_synthetic(self.fixtures())
        self.assertTrue(all(item.verdict=="BASELINE_CPU_CHANGED_INPUT"
                            for item in result))
        self.assertTrue(all(item.baseline_executed for item in result))

    def test_wrong_synthetic_claim_stops_before_cpu_baseline(self):
        a, b = self.fixtures()
        fake = replace(b, claimed_different=("a",))
        with patch("eai.solver_reference_check.reconcile_csv",
                   side_effect=AssertionError("should not execute")):
            outcome = review_candidate_with_cpu_baseline(
                self.store, self.problem, self.candidate, (a, fake))
        self.assertEqual(outcome.disposition,
                         "HOLD_STRUCTURAL_OR_SYNTHETIC_CLAIM")
        self.assertFalse(outcome.baseline_cpu_executed)

    def test_tampered_candidate_stops_before_cpu_baseline(self):
        forged = replace(self.candidate, candidate_sha256="0"*64)
        with patch("eai.solver_reference_check.reconcile_csv",
                   side_effect=AssertionError("should not execute")):
            outcome = review_candidate_with_cpu_baseline(
                self.store, self.problem, forged, self.fixtures())
        self.assertEqual(outcome.results, ())
        self.assertFalse(outcome.composed_candidate_executed)

    def test_identical_source_bytes_are_inconclusive_not_verified(self):
        a = SyntheticComparison("family.identical",
                                (("a", "1"),), (("a", "1"),), ())
        b = self.fixtures()[1]
        results = compare_real_cpu_on_synthetic((a, b))
        self.assertEqual(results[0].verdict,
                         "INCONCLUSIVE_IDENTICAL_SOURCE_BYTES")
        self.assertFalse(results[0].baseline_executed)
        self.assertEqual(results[1].verdict, "BASELINE_CPU_MATCH_UNVERIFIED")

    def test_more_than_twenty_discrepancies_is_inconclusive(self):
        rows1 = tuple(("k%02d"%i, "1") for i in range(22))
        rows2 = tuple(("k%02d"%i, "2") for i in range(22))
        a = SyntheticComparison("family.large", rows1, rows2,
                                tuple("k%02d"%i for i in range(22)))
        b = self.fixtures()[0]
        rows = compare_real_cpu_on_synthetic((a, b))
        self.assertEqual(rows[0].verdict, "INCONCLUSIVE_TOO_MANY_DETAILS")
        self.assertFalse(rows[0].baseline_executed)

    def test_untrusted_non_numeric_and_duplicate_rows_fail_closed(self):
        base = self.fixtures()[1]
        for bad in (
            replace(base, left=(("a", "NaN"),)),
            replace(base, left=(("a", "1"), ("a", "2"))),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                compare_real_cpu_on_synthetic((self.fixtures()[0], bad))

    def test_bounded_family_limit_and_type(self):
        a = self.fixtures()[0]
        with self.assertRaises(ValueError):
            compare_real_cpu_on_synthetic((a,))
        with self.assertRaises(ValueError):
            compare_real_cpu_on_synthetic([a, a])
        with self.assertRaises(ValueError):
            compare_real_cpu_on_synthetic((a, a))

    def test_source_integrity_does_not_modify_original_axnode(self):
        original = {
            h: (self.store.root / "nodes" / (h + ".axnode")).read_bytes()
            for h in self.candidate.node_hashes
        }
        review_candidate_with_cpu_baseline(
            self.store, self.problem, self.candidate, self.fixtures())
        self.assertEqual(original, {
            h: (self.store.root / "nodes" / (h + ".axnode")).read_bytes()
            for h in self.candidate.node_hashes
        })


if __name__ == "__main__":
    unittest.main()
