"""B0/B1 synthetic parity is not a training, promotion or real-world oracle."""
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
from eai.synthetic_candidate_benchmark import benchmark_synthetic_candidate


class B1BenchmarkTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.store=AXNodeStore(Path(t.name)/"nodes")
        self.addCleanup(self.store.close)
        a=self.store.import_node(json.dumps(self.node("data.first",[])))
        b=self.store.import_node(json.dumps(self.node("data.second",[a])))
        self.problem=ProblemSpec.validate({
            "version":1,"id":"synthetic.b1",
            "goal":"PRIVATE never leak synthetic owner words",
            "domain":"data","state_refs":[],"assumptions":[],
            "hard_constraints":[],"objectives":["accuracy"],
            "oracle":"fixture.b0","permissions":["local.read"],
            "budget":{"max_steps":5,"max_seconds":90},"risk":"LOW",
        })
        self.candidate=LogicSynthesizer(self.store).compose(self.problem,(a,b))

    @staticmethod
    def node(name,parents,operator="csv.reconcile.v1"):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"csv":"csv_ref","prior":"difference_receipt"},
                         "output":"difference_receipt"},
            "pre":["synthetic_local_only"],"post":["verify_against_cpu"],
            "steps":[{"skill":operator}],
            "capabilities":["local.read"],"parent_hashes":parents,
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"eai_synthetic","source":"local_only"},
            "budget":{"max_steps":2,"max_seconds":20},
        }

    @staticmethod
    def fixtures():
        train=(
            SyntheticComparison("train.same",(("a","1.0"),),
                                (("a","1.00"),),()),
            SyntheticComparison("train.diff",(("b","2"),),
                                (("b","3"),),("b",)),
        )
        heldout=(
            SyntheticComparison("heldout.same",(("c","5.000"),),
                                (("c","5"),),()),
            SyntheticComparison("heldout.missing",
                                (("d","3"),("e","2")),
                                (("d","3"),("f","2")),("e","f")),
        )
        return train,heldout

    def run_case(self,train=None,heldout=None,candidate=None):
        t,h=self.fixtures()
        return benchmark_synthetic_candidate(
            self.store,self.problem,
            self.candidate if candidate is None else candidate,
            t if train is None else train,
            h if heldout is None else heldout)

    def test_b1_real_synthetic_interpreter_matches_b0_without_uplift_claim(self):
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            report=self.run_case()
        self.assertEqual(report.status,"B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED")
        self.assertEqual(report.train_count,2)
        self.assertEqual(report.heldout_count,2)
        self.assertEqual(report.b0_train_matches,2)
        self.assertEqual(report.b0_heldout_matches,2)
        self.assertEqual(report.b1_train_compared,2)
        self.assertEqual(report.b1_heldout_compared,2)
        self.assertFalse(report.external_truth_verified)
        self.assertFalse(report.permission_to_learn)
        self.assertFalse(report.permission_to_promote)
        self.assertEqual(report.measured_runtime_uplift,"NOT_MEASURED")

    def test_train_claim_poison_prevents_b1_interpretation(self):
        train,heldout=self.fixtures()
        wrong=replace(train[1],claimed_different=())
        with patch("eai.synthetic_candidate_benchmark.interpret_synthetic_candidate",
                   side_effect=AssertionError("must not interpret")):
            report=self.run_case(train=(train[0],wrong))
        self.assertEqual(report.status,"HOLD_B0_UNVERIFIED_OR_LEAK")
        self.assertEqual(report.b1_train_compared,0)

    def test_leaked_duplicate_fixture_rejected_before_execution(self):
        train,heldout=self.fixtures()
        duplicate=replace(train[0],family="heldout.fake",
                          left=(("a","1.00"),),right=(("a","1.0"),))
        with self.assertRaisesRegex(ValueError,"leaked synthetic fixture"):
            self.run_case(heldout=(duplicate,heldout[1]))

    def test_unsupported_candidate_operator_never_verified(self):
        a=self.store.import_node(json.dumps(self.node(
            "data.unsupported_first",[],operator="evidence.verify_receipt.v1")))
        b=self.store.import_node(json.dumps(self.node(
            "data.unsupported_second",[a],operator="evidence.verify_receipt.v1")))
        alternate=LogicSynthesizer(self.store).compose(self.problem,(a,b))
        report=self.run_case(candidate=alternate)
        self.assertEqual(report.status,"HOLD_B1_SYNTHETIC_INTERPRETER_UNSUPPORTED")
        self.assertEqual(report.b1_train_compared,0)

    def test_tampered_b1_verifier_blocks_heldout_result(self):
        from eai.synthetic_candidate_verifier import SyntheticCandidateReceipt
        forged=SyntheticCandidateReceipt(
            "SYNTHETIC_CANDIDATE_COUNTEREXAMPLE_OR_INCONCLUSIVE",
            self.candidate.candidate_sha256,self.problem.digest(),
            "0"*64,(),("train.diff",),False,True)
        with patch("eai.synthetic_candidate_benchmark.verify_synthetic_interpretation",
                   return_value=forged):
            result=self.run_case()
        self.assertEqual(result.status,"HOLD_B1_TRAIN_COUNTEREXAMPLE")
        self.assertEqual(result.b1_heldout_compared,0)

    def test_heldout_verifier_counterexample_blocks_claim(self):
        from eai.synthetic_candidate_verifier import SyntheticCandidateReceipt
        correct=self.run_case()
        self.assertEqual(correct.b1_heldout_compared,2)
        original=__import__("eai.synthetic_candidate_benchmark",
                            fromlist=["verify_synthetic_interpretation"]).verify_synthetic_interpretation
        counter=[0]
        def checker(*args):
            counter[0]+=1
            if counter[0]==2:
                return SyntheticCandidateReceipt(
                    "SYNTHETIC_CANDIDATE_COUNTEREXAMPLE_OR_INCONCLUSIVE",
                    self.candidate.candidate_sha256,self.problem.digest(),
                    "0"*64,(),("heldout.missing",),True,True)
            return original(*args)
        with patch("eai.synthetic_candidate_benchmark.verify_synthetic_interpretation",
                   side_effect=checker):
            report=self.run_case()
        self.assertEqual(report.status,"HOLD_B1_HELDOUT_COUNTEREXAMPLE")
        self.assertEqual(report.b1_heldout_compared,0)

    def test_corrupt_composition_is_not_readily_a_benchmark(self):
        invalid=replace(self.candidate,candidate_sha256="0"*64)
        report=self.run_case(candidate=invalid)
        self.assertEqual(report.status,"HOLD_B0_UNVERIFIED_OR_LEAK")
        self.assertFalse(report.permission_to_promote)

    def test_input_goal_is_never_returned_in_report(self):
        report=self.run_case()
        self.assertNotIn("PRIVATE",str(report))
        self.assertEqual(report,self.run_case())


if __name__=="__main__":
    unittest.main()
