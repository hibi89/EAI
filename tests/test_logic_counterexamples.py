"""Synthetic structural adversarial mutation tests; no semantic oracle claims."""
import json
from pathlib import Path
import tempfile
import unittest

from eai.axnode_store import AXNodeStore
from eai.contracts import ProblemSpec
from eai.logic_synthesis import LogicSynthesizer
from eai.logic_verifier import StructuralVerifier
from eai.logic_counterexamples import probe_structural_counterexamples


class CounterexampleReviewTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.store=AXNodeStore(Path(t.name)/"axnode")
        self.addCleanup(self.store.close)
        self.problem=ProblemSpec.validate({
            "version":1, "id":"synthetic.adversarial",
            "goal":"Check synthetic structure","domain":"data",
            "state_refs":[],"assumptions":[],"hard_constraints":[],
            "objectives":["safety"],"oracle":"offline.oracle",
            "permissions":["local.read"],
            "budget":{"max_steps":3,"max_seconds":90},"risk":"LOW"
        })
        a=self.store.import_node(json.dumps(self.node("data.parent",[])))
        b=self.store.import_node(json.dumps(self.node("data.child",[a])))
        self.candidate=LogicSynthesizer(self.store).compose(self.problem,(a,b))
        self.verifier=StructuralVerifier(self.store)

    @staticmethod
    def node(name, parents):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"in":"difference_receipt","csv":"csv_ref"},
                         "output":"difference_receipt"},
            "pre":["local_only"],"post":["independent_check"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":parents,
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"local_synthetic_only"},
            "budget":{"max_steps":1,"max_seconds":30}
        }

    def test_four_structural_mutations_rejected_without_promoting(self):
        r=probe_structural_counterexamples(
            self.verifier,self.problem,self.candidate)
        self.assertEqual(r.status,"NO_STRUCTURAL_COUNTEREXAMPLE_FOUND_UNVERIFIED")
        self.assertEqual(len(r.tested_cases),4)
        self.assertEqual(r.accepted_forged_cases,())
        self.assertFalse(r.semantic_verified)
        self.assertFalse(r.permits_promotion)

    def test_probe_budget(self):
        result=probe_structural_counterexamples(
            self.verifier,self.problem,self.candidate,max_cases=2)
        self.assertEqual(result.tested_cases,("wrong_hash","fake_authority"))
        with self.assertRaises(ValueError):
            probe_structural_counterexamples(
                self.verifier,self.problem,self.candidate,max_cases=0)

    def test_bad_baseline_rejected_not_verified(self):
        from dataclasses import replace
        corrupted=replace(self.candidate,candidate_sha256="f"*64)
        r=probe_structural_counterexamples(self.verifier,self.problem,corrupted)
        self.assertEqual(r.status,"BASELINE_STRUCTURAL_REJECTED")
        self.assertEqual(r.tested_cases,())

    def test_no_original_node_state_change(self):
        before=[self.store.get(h).as_dict()["status"] for h in self.candidate.node_hashes]
        probe_structural_counterexamples(self.verifier,self.problem,self.candidate)
        self.assertEqual(before,["CANDIDATE","CANDIDATE"])
        self.assertEqual(before,
             [self.store.get(h).as_dict()["status"] for h in self.candidate.node_hashes])


if __name__ == "__main__":
    unittest.main()
