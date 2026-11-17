"""Synthetic-only restricted AXNODE logic composition and verifier regressions."""
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


class LogicSynthesisTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "axnodes"
        self.store = AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        self.synth = LogicSynthesizer(self.store)
        self.verifier = StructuralVerifier(self.store)

    @staticmethod
    def problem(**kwargs):
        data = {
            "version":1, "id":"synthetic.logic",
            "goal":"PRIVATE synthetic composition must stay local",
            "domain":"data", "state_refs":[], "assumptions":[],
            "hard_constraints":[], "objectives":["accuracy"],
            "oracle":"local.synthetic_oracle", "permissions":["local.read"],
            "budget":{"max_steps":5,"max_seconds":90}, "risk":"LOW"
        }
        data.update(kwargs)
        return ProblemSpec.validate(data)

    @staticmethod
    def node(name, parents=None, *, op="csv.reconcile.v1",
             inputs=None, output="difference_receipt"):
        return {
            "schema":"eai.axnode.v1", "id":name, "version":1,
            "kind":"strategy", "status":"CANDIDATE",
            "signature":{"inputs":inputs or {"source":"csv_ref"}, "output":output},
            "pre":["read_only"], "post":["independent_verifier_required"],
            "steps":[{"skill":op}], "capabilities":["local.read"],
            "parent_hashes":parents or [],
            "tests":{"unit":[],"heldout":[],"negative":[]}, "evidence":[],
            "provenance":{"author":"eai_synthetic","source":"synthetic_only"},
            "budget":{"max_steps":2,"max_seconds":20}
        }

    def chain(self, *, inputs=None, op="csv.reconcile.v1"):
        a = self.store.import_node(json.dumps(self.node("data.first")))
        b = self.store.import_node(json.dumps(self.node(
            "data.second", [a], inputs=inputs or {"prior":"difference_receipt"}, op=op)))
        return (a,b)

    def test_strict_two_node_composition_only_structurally_valid(self):
        hashes = self.chain()
        p = self.problem()
        candidate = self.synth.compose(p, hashes)
        receipt = self.verifier.check(p, candidate)
        self.assertEqual(candidate.node_hashes, hashes)
        self.assertEqual(candidate.step_count, 2)
        self.assertEqual(len(candidate.candidate_sha256), 64)
        self.assertEqual(receipt.status, "STRUCTURE_ONLY_UNVERIFIED")
        self.assertFalse(receipt.semantic_verified)
        self.assertFalse(receipt.permits_execution)
        self.assertEqual(self.synth.compose(p, hashes), candidate)

    def test_reversed_node_dependency_and_dangling_graph_rejected(self):
        hashes = self.chain()
        with self.assertRaisesRegex(ValueError, "disconnected dependency"):
            self.synth.compose(self.problem(), tuple(reversed(hashes)))
        with self.assertRaises(KeyError):
            self.synth.compose(self.problem(), (hashes[0], "f"*64))

    def test_incompatible_parent_output_type_rejected(self):
        hashes = self.chain(inputs={"prior":"text"})
        with self.assertRaisesRegex(ValueError, "output type"):
            self.synth.compose(self.problem(), hashes)

    def test_required_forbidden_constraints_and_unknowns_rejected(self):
        hashes = self.chain()
        for conditions in (
            ["must:data.absent"], ["forbid:data.second"],
            ["must:data.first","forbid:data.first"],
            ["ignore all rules"],
        ):
            with self.subTest(conditions=conditions), self.assertRaises(ValueError):
                self.synth.compose(self.problem(hard_constraints=conditions), hashes)

    def test_permission_budget_and_risk_gates(self):
        hashes = self.chain()
        cases = [
            self.problem(permissions=["pure"]),
            self.problem(budget={"max_steps":1,"max_seconds":50}),
            self.problem(budget={"max_steps":3,"max_seconds":10}),
            self.problem(risk="HIGH"),
        ]
        for p in cases:
            with self.subTest(problem=p.id), self.assertRaises(ValueError):
                self.synth.compose(p, hashes)

    def test_hash_receipt_and_trust_forgery_denied(self):
        hashes = self.chain()
        p = self.problem()
        good = self.synth.compose(p, hashes)
        for forged in (
            replace(good,candidate_sha256="0"*64),
            replace(good,trust="VERIFIED"),
            replace(good,step_count=999),
            replace(good,node_hashes=tuple(reversed(hashes))),
        ):
            with self.subTest(forged=forged):
                self.assertEqual(self.verifier.check(p, forged).status,
                                 "REJECTED_UNVERIFIED")

    def test_wrong_problem_digest_cannot_be_reused(self):
        hashes = self.chain()
        a = self.problem()
        candidate = self.synth.compose(a, hashes)
        b = self.problem(id="synthetic.other")
        self.assertEqual(self.verifier.check(b,candidate).status, "REJECTED_UNVERIFIED")

    def test_unsupported_operator_rejected_before_any_execution(self):
        hashes = self.chain(op="csv.sha256.v1")
        with self.assertRaisesRegex(ValueError, "unapproved composition"):
            self.synth.compose(self.problem(), hashes)

    def test_source_tamper_rejected_in_builder_and_verifier(self):
        hashes = self.chain()
        p = self.problem()
        candidate = self.synth.compose(p, hashes)
        (self.root / "nodes" / (hashes[1]+".axnode")).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.synth.compose(p, hashes)
        self.assertEqual(self.verifier.check(p,candidate).status,"REJECTED_UNVERIFIED")

    def test_no_network_and_no_automatic_node_promotion(self):
        hashes = self.chain()
        before = {h:(self.root/"nodes"/(h+".axnode")).read_bytes() for h in hashes}
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            candidate = self.synth.compose(self.problem(), hashes)
            receipt = self.verifier.check(self.problem(), candidate)
        self.assertEqual(receipt.status,"STRUCTURE_ONLY_UNVERIFIED")
        self.assertEqual(before,{h:(self.root/"nodes"/(h+".axnode")).read_bytes() for h in hashes})
        self.assertEqual({self.store.get(h).as_dict()["status"] for h in hashes},
                         {"CANDIDATE"})

    def test_bounds_and_forged_candidate_input_type_rejected(self):
        hashes = self.chain()
        p = self.problem()
        for invalid in [hashes[:1], hashes+hashes, list(hashes), tuple(["f"*64]*5)]:
            with self.assertRaises((ValueError,KeyError,TypeError)):
                self.synth.compose(p, invalid)
        with self.assertRaises(ValueError):
            self.synth.compose(p, (hashes[0], hashes[0]))


if __name__ == "__main__":
    unittest.main()
