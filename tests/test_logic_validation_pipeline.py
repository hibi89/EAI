"""No promotion or execution from structural and synthetic verification."""
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
from eai.logic_oracle import SyntheticComparison
from eai.logic_validation_pipeline import review_synthesis_candidate


class ValidationPipelineTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store=AXNodeStore(Path(temp.name)/"synthetic")
        self.addCleanup(self.store.close)
        a=self.store.import_node(json.dumps(self.node("data.first",[])))
        b=self.store.import_node(json.dumps(self.node("data.second",[a])))
        self.problem=ProblemSpec.validate({
            "version":1,"id":"synthetic.pipeline","goal":"PRIVATE synthetic",
            "domain":"data","state_refs":[],"assumptions":[],
            "hard_constraints":[],"objectives":["accuracy"],
            "oracle":"synthetic.fixture","permissions":["local.read"],
            "budget":{"max_steps":5,"max_seconds":60},"risk":"LOW",
        })
        self.candidate=LogicSynthesizer(self.store).compose(self.problem,(a,b))

    @staticmethod
    def node(name,parents):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"csv":"csv_ref","prior":"difference_receipt"},
                         "output":"difference_receipt"},
            "pre":["authorized_read_only"],"post":["independent_check"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":parents,
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"synthetic_only"},
            "budget":{"max_steps":2,"max_seconds":15},
        }

    @staticmethod
    def fixtures():
        return (
            SyntheticComparison("family.same",
                                (("a","1"),),(("a","1.00"),),()),
            SyntheticComparison("family.mismatch",
                                (("a","1"),),(("a","3"),),("a",)),
        )

    def test_structural_synthetic_matches_are_only_unverified(self):
        r=review_synthesis_candidate(self.store,self.problem,
                                     self.candidate,self.fixtures())
        self.assertEqual(r.disposition,"SYNTHETIC_EVIDENCE_ONLY_NOT_PROMOTED")
        self.assertEqual(r.structural_status,"STRUCTURE_ONLY_UNVERIFIED")
        self.assertEqual(r.synthetic_oracle_status,"SYNTHETIC_CLAIMS_MATCH_UNVERIFIED")
        self.assertEqual(r.counterexample_families,())
        self.assertEqual(r.node_promotion,"FORBIDDEN_UNVERIFIED")
        self.assertEqual(r.execution,"FORBIDDEN_UNVERIFIED")
        self.assertFalse(r.independent_real_world_oracle)

    def test_counterexample_quarantines_proposal_without_mutation(self):
        a,b=self.fixtures()
        forged=replace(b,claimed_different=())
        r=review_synthesis_candidate(self.store,self.problem,
                                     self.candidate,(a,forged))
        self.assertEqual(r.disposition,"QUARANTINE_REVIEW_REQUIRED")
        self.assertEqual(r.counterexample_families,("family.mismatch",))
        self.assertEqual({self.store.get(h).as_dict()["status"] for h in
                          self.candidate.node_hashes},{"CANDIDATE"})

    def test_invalid_candidate_halts_before_running_oracle(self):
        bad=replace(self.candidate,candidate_sha256="0"*64)
        r=review_synthesis_candidate(self.store,self.problem,bad,self.fixtures())
        self.assertEqual(r.structural_status,"REJECTED_UNVERIFIED")
        self.assertEqual(r.adversarial_status,"NOT_RUN")
        self.assertEqual(r.synthetic_oracle_status,"NOT_RUN")
        self.assertEqual(r.disposition,"QUARANTINE_REVIEW_REQUIRED")

    def test_private_goal_is_not_reported_and_network_disabled(self):
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            r=review_synthesis_candidate(self.store,self.problem,
                                         self.candidate,self.fixtures())
        self.assertNotIn("PRIVATE",str(r))
        self.assertFalse(r.independent_real_world_oracle)

    def test_wrong_type_and_empty_fixtures_fail_closed(self):
        with self.assertRaises(ValueError):
            review_synthesis_candidate(self.store,self.problem,self.candidate,[])
        with self.assertRaises(ValueError):
            review_synthesis_candidate(self.store,self.problem,self.candidate,())


if __name__=="__main__":
    unittest.main()
