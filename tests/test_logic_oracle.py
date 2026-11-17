"""Synthetic fixture-only independent reference math: never tests actual AXNODE execution."""
from dataclasses import replace
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.contracts import ProblemSpec
from eai.logic_synthesis import LogicSynthesizer
from eai.logic_verifier import StructuralVerifier
from eai.logic_oracle import SyntheticComparison, SyntheticReconciliationOracle


class SyntheticOracleTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store=AXNodeStore(Path(temp.name)/"isolated")
        self.addCleanup(self.store.close)
        a=self.store.import_node(json.dumps(self.node("data.first",[])))
        b=self.store.import_node(json.dumps(self.node("data.second",[a])))
        self.problem=self.problem_spec()
        self.candidate=LogicSynthesizer(self.store).compose(self.problem,(a,b))
        self.oracle=SyntheticReconciliationOracle(StructuralVerifier(self.store))

    @staticmethod
    def node(name,parents):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"csv":"csv_ref","prior":"difference_receipt"},
                         "output":"difference_receipt"},
            "pre":["authorized_read_only"],"post":["verify_later"],
            "steps":[{"skill":"csv.reconcile.v1"}],"capabilities":["local.read"],
            "parent_hashes":parents,"tests":{"unit":[],"heldout":[],"negative":[]},
            "evidence":[],"provenance":{"author":"EAI_DESIGN","source":"synthetic_only"},
            "budget":{"max_steps":2,"max_seconds":20},
        }

    @staticmethod
    def problem_spec(**overrides):
        payload={
            "version":1,"id":"synthetic.oracle","goal":"synthetic data",
            "domain":"data","state_refs":[],"assumptions":[],
            "hard_constraints":[],"objectives":["accuracy"],
            "oracle":"synthetic.reference","permissions":["local.read"],
            "budget":{"max_steps":5,"max_seconds":60},"risk":"LOW",
        }
        payload.update(overrides)
        return ProblemSpec.validate(payload)

    @staticmethod
    def fixtures():
        return (
            SyntheticComparison("family.agree",
                                (("a","1.00"),("b","2.5")),
                                (("a","1"),("b","2.50")),()),
            SyntheticComparison("family.missing",
                                (("a","1"),("b","2")),
                                (("a","4"),("c","2")),("a","b","c")),
        )

    def test_mathematical_claims_match_without_verifying_candidate(self):
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            verdict=self.oracle.check(self.problem,self.candidate,self.fixtures())
        self.assertEqual(verdict.status,"SYNTHETIC_CLAIMS_MATCH_UNVERIFIED")
        self.assertEqual(verdict.counterexamples,())
        self.assertTrue(verdict.independent_fixture_math)
        self.assertFalse(verdict.candidate_executed)
        self.assertFalse(verdict.semantic_verified)
        self.assertFalse(verdict.grants_promotion)

    def test_forged_discrepancy_is_a_counterexample(self):
        good,bad=self.fixtures()
        fake=replace(bad,claimed_different=("a",))
        verdict=self.oracle.check(self.problem,self.candidate,(good,fake))
        self.assertEqual(verdict.status,"SYNTHETIC_COUNTEREXAMPLE_FOUND")
        self.assertEqual(verdict.counterexamples,("family.missing",))

    def test_tampered_candidate_rejected_before_reference_math(self):
        forged=replace(self.candidate,candidate_sha256="0"*64)
        result=self.oracle.check(self.problem,forged,self.fixtures())
        self.assertEqual(result.status,"STRUCTURAL_BASELINE_REJECTED")
        self.assertFalse(result.independent_fixture_math)

    def test_high_risk_is_not_falsely_claimed_safe(self):
        high=self.problem_spec(risk="HIGH")
        result=self.oracle.check(high,self.candidate,self.fixtures())
        self.assertEqual(result.status,"HIGH_RISK_BLOCKED")
        self.assertFalse(result.grants_promotion)

    def test_unsafe_decimal_and_duplicate_keys_rejected(self):
        okay=self.fixtures()[1]
        for badrows in (
            (("a","NaN"),), (("a","1e12"),),
            (("a","1"),("a","2")), (("../sensitive","3"),),
        ):
            bad=replace(self.fixtures()[0],left=badrows)
            with self.subTest(rows=badrows),self.assertRaises(ValueError):
                self.oracle.check(self.problem,self.candidate,(bad,okay))

    def test_duplicate_family_and_unordered_claims_rejected(self):
        a,b=self.fixtures()
        for bad in (replace(b,family=a.family),
                    replace(b,claimed_different=("c","a")),
                    replace(b,claimed_different=("a","a"))):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                self.oracle.check(self.problem,self.candidate,(a,bad))

    def test_bounded_fixtures_no_single_training_example_acceptance(self):
        a,b=self.fixtures()
        for fixtures in ((a,),(),(a,)*13):
            with self.assertRaises(ValueError):
                self.oracle.check(self.problem,self.candidate,fixtures)
        self.assertEqual(self.oracle.check(self.problem,self.candidate,(a,b)), 
                         self.oracle.check(self.problem,self.candidate,(a,b)))


if __name__=="__main__":
    unittest.main()
