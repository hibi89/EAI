"""Synthetic-only local architect proposals; no network or execution."""
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.contracts import ProblemSpec
from eai.axnode_store import AXNodeStore
from eai.axnode_retrieval import AXNodeRetriever
from eai.problem_model import ProblemModeler
from eai.design_engine import DesignEngine


class DesignEngineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "sandbox"
        self.store = AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        self.retriever = AXNodeRetriever(self.store)
        self.engine = DesignEngine(ProblemModeler(self.retriever))

    @staticmethod
    def problem(**overrides):
        raw = {
            "version":1, "id":"synthetic.compare", "goal":"Compare local fixtures",
            "domain":"data", "state_refs":["fixture.a"],
            "assumptions":["Owner provided synthetic examples"],
            "hard_constraints":[], "objectives":["accuracy"],
            "oracle":"fixture.compare", "permissions":["local.read"],
            "budget":{"max_steps":4,"max_seconds":60}, "risk":"LOW",
        }
        raw.update(overrides)
        return ProblemSpec.validate(raw)

    @staticmethod
    def node(identifier):
        return {
            "schema":"eai.axnode.v1","id":identifier,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"left":"csv_ref"},"output":"difference_receipt"},
            "pre":["authorized_read_only_sources"],
            "post":["independent_receipt_needed"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":[],
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"local_verified_only"},
            "budget":{"max_steps":3,"max_seconds":30},
        }

    def populate(self):
        a = self.store.import_node(json.dumps(self.node("data.strategy_a")))
        b = self.store.import_node(json.dumps(self.node("data.strategy_b")))
        return a, b

    def test_two_distinct_evidence_pinned_designs_are_unverified(self):
        a, b = self.populate()
        p = self.problem()
        outcome = self.engine.propose(p)
        self.assertEqual(outcome.design.problem_sha256, p.digest())
        self.assertEqual(len(outcome.design.alternatives), 2)
        refs = [option[1] for option in outcome.design.alternatives]
        self.assertNotEqual(refs[0], refs[1])
        self.assertEqual({a,b}, set(outcome.result.evidence_sha256))
        self.assertEqual(outcome.result.status, "UNVERIFIED")
        self.assertTrue(all(item.status == "UNVERIFIED" for item in outcome.analysis.evidence))
        self.assertIn("oracle_unverified", outcome.result.unknowns)
        self.assertIn("state_unverified:fixture.a", outcome.result.unknowns)
        self.assertEqual(self.engine.propose(p), outcome)

    def test_contradictory_constraints_never_produce_design(self):
        self.populate()
        p = self.problem(hard_constraints=["must:data.strategy_a", "forbid:data.strategy_a"])
        result = self.engine.propose(p)
        self.assertEqual(result.result.status, "CONFLICT")
        self.assertEqual(result.analysis.contradictions, ("data.strategy_a",))
        self.assertEqual(result.design.alternatives, ())
        self.assertEqual(result.design.blocked_reason, "CONTRADICTORY_HARD_CONSTRAINTS")

    def test_opaque_natural_language_constraints_yield_unknown(self):
        self.populate()
        result = self.engine.propose(self.problem(hard_constraints=["Do whatever seems best"]))
        self.assertEqual(result.design.alternatives, ())
        self.assertEqual(result.design.blocked_reason, "UNINTERPRETED_HARD_CONSTRAINTS")
        self.assertIn("constraint_unparsed:0", result.analysis.unknowns)

    def test_missing_required_strategy_is_blocked(self):
        self.populate()
        result = self.engine.propose(self.problem(hard_constraints=["must:data.absent"]))
        self.assertEqual(result.design.alternatives, ())
        self.assertEqual(result.design.blocked_reason, "REQUIRED_STRATEGY_NOT_AVAILABLE")

    def test_forbidden_strategy_is_never_recommended(self):
        self.populate()
        result = self.engine.propose(self.problem(hard_constraints=["forbid:data.strategy_b"]))
        self.assertEqual(result.design.alternatives, ())
        self.assertEqual(result.design.blocked_reason, "INSUFFICIENT_DISTINCT_LOCAL_STRATEGIES")
        self.assertEqual([x.strategy_id for x in result.analysis.evidence], ["data.strategy_a"])

    def test_required_strategy_retained_in_every_option(self):
        self.populate()
        result = self.engine.propose(self.problem(hard_constraints=["must:data.strategy_a"]))
        self.assertEqual(len(result.design.alternatives), 2)
        self.assertTrue(all("data.strategy_a" in option[1]
                            for option in result.design.alternatives))

    def test_single_candidate_and_high_risk_abstain(self):
        self.store.import_node(json.dumps(self.node("data.strategy_a")))
        self.assertEqual(self.engine.propose(self.problem()).design.blocked_reason,
                         "INSUFFICIENT_DISTINCT_LOCAL_STRATEGIES")
        self.store.import_node(json.dumps(self.node("data.strategy_b")))
        high = self.engine.propose(self.problem(risk="HIGH"))
        self.assertEqual(high.design.blocked_reason,
                         "HIGH_RISK_REQUIRES_INDEPENDENT_REVIEW")

    def test_tampering_rejected_and_never_executed(self):
        self.populate()
        target = self.store.hashes()[0]
        (self.root / "nodes" / (target + ".axnode")).write_bytes(b"malicious")
        with self.assertRaises(ValueError):
            self.engine.propose(self.problem())

    def test_no_cloud_no_external_data_and_no_original_writes(self):
        self.populate()
        before = {digest: (self.root / "nodes" / (digest + ".axnode")).read_bytes()
                  for digest in self.store.hashes()}
        with patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.engine.propose(self.problem(goal="PRIVATE source stays local"))
        after = {digest: (self.root / "nodes" / (digest + ".axnode")).read_bytes()
                 for digest in self.store.hashes()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
