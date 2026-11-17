"""B0-only held-out synthetic tests; candidate never executed or scored."""
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
from eai.synthetic_holdout import compare_b0_train_and_heldout


class B0HeldoutTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = AXNodeStore(Path(tmp.name)/"axnodes")
        self.addCleanup(self.store.close)
        a=self.store.import_node(json.dumps(self.node("data.first",[])))
        b=self.store.import_node(json.dumps(self.node("data.second",[a])))
        self.problem=ProblemSpec.validate({
            "version":1,"id":"synthetic.b0", "goal":"PRIVATE synthetic test",
            "domain":"data","state_refs":[],"assumptions":[],
            "hard_constraints":[],"objectives":["accuracy"],
            "oracle":"synthetic.oracle","permissions":["local.read"],
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
            "tests":{"unit":[],"heldout":[],"negative":[]}, "evidence":[],
            "provenance":{"author":"eai_synthetic","source":"local_only"},
            "budget":{"max_steps":2,"max_seconds":15},
        }

    @staticmethod
    def data():
        train=(
            SyntheticComparison("train.same",(("a","1.0"),),
                                (("a","1.00"),),()),
            SyntheticComparison("train.diff",(("a","2"),("b","1")),
                                (("a","8"),("b","1")),("a",)),
        )
        heldout=(
            SyntheticComparison("heldout.missing",(("c","1"),("d","2")),
                                (("c","1"),("e","3")),("d","e")),
            SyntheticComparison("heldout.same",(("g","7.0"),),
                                (("g","7.00"),),()),
        )
        return train, heldout

    def run_b0(self,train=None,heldout=None):
        a,b=self.data()
        return compare_b0_train_and_heldout(
            self.store,self.problem,self.candidate,
            a if train is None else train,
            b if heldout is None else heldout)

    def test_four_independent_families_b0_only(self):
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            r=self.run_b0()
        self.assertEqual(r.status,"B0_SYNTHETIC_HELDOUT_MATCH_UNVERIFIED")
        self.assertEqual(r.training_cpu_matches,2)
        self.assertEqual(r.heldout_cpu_matches,2)
        self.assertEqual(r.observed_b0_cases,4)
        self.assertFalse(r.candidate_b1_evaluated)
        self.assertFalse(r.candidate_b2_evaluated)
        self.assertEqual(r.verified_uplift,"NOT_MEASURED")
        self.assertFalse(r.supports_activation)

    def test_training_claim_poison_stops_before_heldout(self):
        train,heldout=self.data()
        poisoned=replace(train[1],claimed_different=())
        with patch("eai.solver_reference_check.reconcile_csv",
                   wraps=__import__("eai.reconcile_csv",
                                    fromlist=["reconcile_csv"]).reconcile_csv) as run:
            result=self.run_b0(train=(train[0],poisoned))
        self.assertEqual(result.status,"HOLD_B0_TRAINING_FAILURE")
        self.assertEqual(result.heldout_cpu_matches,0)
        self.assertEqual(result.observed_b0_cases,0)
        self.assertEqual(run.call_count,0)

    def test_heldout_poison_causes_hold(self):
        train,heldout=self.data()
        poisoned=replace(heldout[0],claimed_different=("d",))
        result=self.run_b0(heldout=(poisoned,heldout[1]))
        self.assertEqual(result.status,"HOLD_B0_HELDOUT_FAILURE")
        self.assertFalse(result.supports_activation)

    def test_cross_split_duplicate_bytes_rejected_even_with_new_family(self):
        train,heldout=self.data()
        duplicate=replace(train[0],family="heldout.fake")
        with self.assertRaisesRegex(ValueError,"leaked synthetic fixture"):
            self.run_b0(heldout=(duplicate,heldout[1]))

    def test_cross_split_duplicate_family_rejected(self):
        train,heldout=self.data()
        duplicate=replace(heldout[0],family=train[0].family)
        with self.assertRaises(ValueError):
            self.run_b0(heldout=(duplicate,heldout[1]))

    def test_too_few_holdout_families_rejected(self):
        _,heldout=self.data()
        with self.assertRaises(ValueError):
            self.run_b0(heldout=heldout[:1])

    def test_forged_actual_cpu_output_never_claims_b0_pass(self):
        with patch("eai.solver_reference_check.reconcile_csv",
                   return_value={"status":"AGREE","counts":{},
                                 "differences":[],"truncated":0,"sources":[]}):
            outcome=self.run_b0()
        self.assertEqual(outcome.status,"HOLD_B0_TRAINING_FAILURE")
        self.assertEqual(outcome.heldout_cpu_matches,0)


if __name__=="__main__":
    unittest.main()
