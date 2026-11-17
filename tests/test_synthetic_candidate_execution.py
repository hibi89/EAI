"""C14 synthetic AXNODE interpretation/independent CPU oracle regression gates."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.contracts import ProblemSpec, canonical_bytes
from eai.logic_oracle import SyntheticComparison
from eai.logic_synthesis import LogicSynthesizer
from eai.synthetic_candidate_interpreter import interpret_synthetic_candidate
from eai.synthetic_candidate_verifier import verify_synthetic_interpretation


class SyntheticCandidateExecutionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"axnodes"
        self.store=AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        a=self.store.import_node(json.dumps(self.node("data.first",[])))
        b=self.store.import_node(json.dumps(self.node("data.second",[a])))
        self.problem=self.problem_spec()
        self.candidate=LogicSynthesizer(self.store).compose(
            self.problem,(a,b))

    @staticmethod
    def node(name,parents,skill="csv.reconcile.v1"):
        return {
            "schema":"eai.axnode.v1", "id":name, "version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"csv":"csv_ref","previous":"difference_receipt"},
                         "output":"difference_receipt"},
            "pre":["authorized_synthetic_only"],
            "post":["independent_reference_required"],
            "steps":[{"skill":skill}],
            "capabilities":["local.read"],"parent_hashes":parents,
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"eai_synthetic","source":"local_only"},
            "budget":{"max_steps":2,"max_seconds":10},
        }

    @staticmethod
    def problem_spec(**overrides):
        data={
            "version":1,"id":"synthetic.candidate",
            "goal":"PRIVATE synthetic evidence never exported",
            "domain":"data","state_refs":[],"assumptions":[],
            "hard_constraints":[],"objectives":["safety"],
            "oracle":"synthetic.reference","permissions":["local.read"],
            "budget":{"max_steps":5,"max_seconds":60},"risk":"LOW",
        }
        data.update(overrides)
        return ProblemSpec.validate(data)

    @staticmethod
    def fixtures():
        return (
            SyntheticComparison("family.agree",
                                (("a","1.0"),("b","2.00")),
                                (("a","1.00"),("b","2")),()),
            SyntheticComparison("family.mismatch",
                                (("a","1"),("b","2")),
                                (("a","3"),("c","4")),("a","b","c")),
        )

    def run_synthetic(self, fixtures=None):
        return interpret_synthetic_candidate(
            self.store,self.problem,self.candidate,
            self.fixtures() if fixtures is None else fixtures)

    def verify(self,witness,fixtures=None):
        return verify_synthetic_interpretation(
            self.store,self.problem,self.candidate,
            self.fixtures() if fixtures is None else fixtures,witness)

    def test_real_typed_candidate_chain_interpreted_and_cpu_matched(self):
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            witness=self.run_synthetic()
            receipt=self.verify(witness)
        self.assertEqual(witness.disposition,"SYNTHETIC_INTERPRETED_UNVERIFIED")
        self.assertEqual(witness.families[0].difference_count,0)
        self.assertEqual(witness.families[1].difference_count,3)
        self.assertEqual(len(witness.steps),2)
        self.assertTrue(witness.sandbox_candidate_interpreted)
        self.assertEqual(receipt.status,"SYNTHETIC_CANDIDATE_CPU_MATCH_UNVERIFIED")
        self.assertEqual(receipt.checked_families,
                         ("family.agree","family.mismatch"))
        self.assertTrue(receipt.independent_cpu_executed)
        self.assertTrue(receipt.interpretation_executed)
        self.assertFalse(receipt.real_world_verified)
        self.assertFalse(receipt.permits_promotion)
        self.assertFalse(receipt.permits_learning)

    def test_interpretation_witness_is_deterministic_and_does_not_change_node(self):
        before={h:(self.root/"nodes"/(h+".axnode")).read_bytes()
                for h in self.candidate.node_hashes}
        self.assertEqual(self.run_synthetic(),self.run_synthetic())
        self.assertEqual(before,{h:(self.root/"nodes"/(h+".axnode")).read_bytes()
                                 for h in self.candidate.node_hashes})

    def test_changed_witness_digest_is_rejected_before_baseline(self):
        corrupted=replace(self.run_synthetic(),witness_sha256="0"*64)
        with patch("eai.synthetic_candidate_verifier.compare_real_cpu_on_synthetic",
                   side_effect=AssertionError("must not run")):
            decision=self.verify(corrupted)
        self.assertEqual(decision.status,"REJECTED_TAMPERED_SYNTHETIC_WITNESS")
        self.assertFalse(decision.independent_cpu_executed)

    def test_changed_step_identity_is_rejected_before_baseline(self):
        valid=self.run_synthetic()
        forged_step=replace(valid.steps[0],step_index=1)
        forged=replace(valid,steps=(forged_step,valid.steps[1]))
        decision=self.verify(forged)
        self.assertEqual(decision.status,"REJECTED_INVALID_SYNTHETIC_WITNESS")

    def test_forged_counterexample_even_with_recomputed_digest_is_rejected(self):
        valid=self.run_synthetic()
        fake=replace(valid.families[1],difference_count=1)
        serialized={
            "schema":"eai.synthetic.candidate.execution.v1",
            "problem_sha256":valid.problem_sha256,
            "candidate_sha256":valid.candidate_sha256,
            "steps":[[s.node_sha256,s.output_type,s.step_index]
                     for s in valid.steps],
            "families":[[f.family,f.difference_sha256,f.difference_count,
                         f.executed_steps]
                        for f in (valid.families[0],fake)],
        }
        newhash=hashlib.sha256(canonical_bytes(serialized)).hexdigest()
        forged=replace(valid,families=(valid.families[0],fake),
                       witness_sha256=newhash)
        result=self.verify(forged)
        self.assertEqual(
            result.status,"SYNTHETIC_CANDIDATE_COUNTEREXAMPLE_OR_INCONCLUSIVE")
        self.assertEqual(result.counterexample_families,("family.mismatch",))

    def test_forged_semantic_execution_rights_denied(self):
        valid=self.run_synthetic()
        forged=replace(valid,real_world_verified=True,permits_promotion=True)
        receipt=self.verify(forged)
        self.assertEqual(receipt.status,"REJECTED_INVALID_SYNTHETIC_WITNESS")
        self.assertFalse(receipt.permits_promotion)

    def test_malformed_duplicate_family_and_unsafe_decimal_rejected(self):
        a,b=self.fixtures()
        for pair in ((a,a),(a,replace(b,left=(("a","NaN"),))),
                     (a,replace(b,left=(("a","1"),("a","1"))))):
            with self.subTest(case=pair),self.assertRaises(ValueError):
                self.run_synthetic(pair)

    def test_medium_or_high_risk_or_lack_of_permission_rejected(self):
        for altered in (self.problem_spec(risk="MEDIUM"),
                        self.problem_spec(risk="HIGH"),
                        self.problem_spec(permissions=["pure"])):
            with self.subTest(risk=altered.risk),self.assertRaises(ValueError):
                interpret_synthetic_candidate(self.store,altered,
                                              self.candidate,self.fixtures())

    def test_unsupported_receipt_verification_operator_cannot_self_certify(self):
        a=self.store.import_node(json.dumps(self.node(
            "data.verify_a",[],skill="evidence.verify_receipt.v1")))
        b=self.store.import_node(json.dumps(self.node(
            "data.verify_b",[a],skill="evidence.verify_receipt.v1")))
        alt=LogicSynthesizer(self.store).compose(self.problem,(a,b))
        with self.assertRaisesRegex(ValueError,"unsafe synthetic operator"):
            interpret_synthetic_candidate(self.store,self.problem,alt,
                                          self.fixtures())

    def test_changed_composition_hash_never_becomes_executed(self):
        invalid=replace(self.candidate,candidate_sha256="f"*64)
        with self.assertRaisesRegex(ValueError,"structural candidate"):
            interpret_synthetic_candidate(self.store,self.problem,invalid,
                                          self.fixtures())

    def test_unchecked_new_family_does_not_inherit_old_witness(self):
        original=self.run_synthetic()
        fixtures=(self.fixtures()[0],
                  replace(self.fixtures()[1],family="family.other"))
        receipt=self.verify(original,fixtures=fixtures)
        self.assertEqual(receipt.status,"REJECTED_INVALID_SYNTHETIC_FAMILY")
        self.assertFalse(receipt.independent_cpu_executed)

    def test_disallowed_fixture_count_never_interprets(self):
        with self.assertRaises(ValueError):
            self.run_synthetic(self.fixtures()[:1])
        with self.assertRaises(ValueError):
            self.run_synthetic(self.fixtures()*7)


if __name__=="__main__":
    unittest.main()
