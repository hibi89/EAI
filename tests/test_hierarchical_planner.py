"""Synthetic-only bounded EAI V3-06 planner; proposals NEVER execute skills."""
import copy
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.axnode_retrieval import AXNodeRetriever
from eai.contracts import ProblemSpec
from eai.problem_model import ProblemModeler
from eai.design_engine import DesignEngine
from eai.hierarchical_planner import HierarchicalPlanner


class HierarchicalPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "synthetic"
        self.store = AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        self.designer = DesignEngine(ProblemModeler(AXNodeRetriever(self.store)))
        self.planner = HierarchicalPlanner(self.store)

    @staticmethod
    def node(name, *, parents=(), op="csv.reconcile.v1", inputs=None,
             capabilities=None, max_seconds=20):
        return {
            "schema": "eai.axnode.v1", "id": name, "version": 1,
            "kind": "strategy", "status": "CANDIDATE",
            "signature": {"inputs": inputs or {"source": "csv_ref"},
                          "output": "difference_receipt"},
            "pre": ["authorized_only"], "post": ["independent_check_required"],
            "steps": [{"skill": op}],
            "capabilities": capabilities if capabilities is not None else ["local.read"],
            "parent_hashes": list(parents),
            "tests": {"unit": [], "heldout": [], "negative": []}, "evidence": [],
            "provenance": {"author": "EAI_DESIGN", "source": "synthetic_only"},
            "budget": {"max_steps": 2, "max_seconds": max_seconds},
        }

    @staticmethod
    def problem(**overrides):
        raw = {
            "version": 1, "id": "synthetic.plan",
            "goal": "Keep plan advisory", "domain": "data",
            "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["accuracy"],
            "oracle": "fixture.compare", "permissions": ["local.read"],
            "budget": {"max_steps": 4, "max_seconds": 60}, "risk": "LOW",
        }
        raw.update(overrides)
        return ProblemSpec.validate(raw)

    def import_two(self):
        a = self.store.import_node(json.dumps(self.node("data.first")))
        b = self.store.import_node(json.dumps(self.node("data.second")))
        return a, b

    def test_typed_candidates_are_ranked_but_never_verified(self):
        a, b = self.import_two()
        p = self.problem()
        report = self.planner.plan(p, self.designer.propose(p))
        self.assertEqual(report.status, "CANDIDATES_UNVERIFIED")
        self.assertEqual(len(report.candidates), 2)
        self.assertEqual(report.expansions, 2)
        self.assertEqual({x.node_hashes[0] for x in report.candidates}, {a, b})
        for c in report.candidates:
            self.assertEqual(c.plan.problem_sha256, p.digest())
            self.assertEqual(c.plan.steps[0][1], "csv.reconcile.v1")
            self.assertEqual(c.plan.steps[0][3], "local.read")
            self.assertEqual(c.trust, "ADVISORY_UNVERIFIED_NOT_EXECUTED")
            self.assertEqual(c.declared_step_count, 1)
        self.assertEqual(self.planner.plan(p, self.designer.propose(p)), report)

    def test_no_permission_no_advisory_step(self):
        self.import_two()
        p = self.problem(permissions=["pure"])
        report = self.planner.plan(p, self.designer.propose(p))
        self.assertEqual(report.status, "BLOCKED")
        self.assertTrue(all(code == "PLAN_CAPABILITY_NOT_AUTHORIZED"
                            for _, code in report.blocked))

    def test_parent_included_topologically_with_type_checked_effect(self):
        parent = self.store.import_node(json.dumps(self.node("data.first")))
        self.store.import_node(json.dumps(self.node(
            "data.second", parents=(parent,),
            inputs={"prior": "difference_receipt"})))
        p = self.problem(hard_constraints=["must:data.first"])
        report = self.planner.plan(p, self.designer.propose(p))
        self.assertEqual(len(report.candidates), 2)
        chained = next(c for c in report.candidates if len(c.node_hashes) == 2)
        self.assertEqual(chained.plan.steps[1][2], ("step01",))
        self.assertEqual(chained.declared_step_count, 2)

    def test_missing_parent_never_silently_included(self):
        parent = self.store.import_node(json.dumps(self.node("data.first")))
        self.store.import_node(json.dumps(self.node(
            "data.second", parents=(parent,),
            inputs={"prior": "difference_receipt"})))
        p = self.problem()
        report = self.planner.plan(p, self.designer.propose(p))
        self.assertEqual(len(report.candidates), 1)
        self.assertTrue(any(code == "MISSING_OR_CYCLIC_NODE_PARENT"
                            for _, code in report.blocked))

    def test_invalid_parent_output_type_is_blocked(self):
        parent = self.store.import_node(json.dumps(self.node("data.first")))
        self.store.import_node(json.dumps(self.node("data.second", parents=(parent,))))
        p = self.problem(hard_constraints=["must:data.first"])
        report = self.planner.plan(p, self.designer.propose(p))
        self.assertTrue(any(code == "INCOMPATIBLE_PARENT_OUTPUT_TYPE"
                            for _, code in report.blocked))

    def test_unknown_non_plan_operator_rejected(self):
        self.store.import_node(json.dumps(self.node("data.first", op="csv.sha256.v1")))
        self.store.import_node(json.dumps(self.node("data.second", op="csv.sha256.v1")))
        p = self.problem()
        report = self.planner.plan(p, self.designer.propose(p))
        self.assertEqual(report.status, "BLOCKED")
        self.assertTrue(all(c == "UNSUPPORTED_PLAN_OPERATOR"
                            for _, c in report.blocked))

    def test_budget_rejected_without_running_a_step(self):
        self.import_two()
        p = self.problem(budget={"max_steps": 1, "max_seconds": 10})
        report = self.planner.plan(p, self.designer.propose(p))
        self.assertTrue(all(code == "PLAN_RESOURCE_BUDGET_EXCEEDED"
                            for _, code in report.blocked))
        self.assertEqual(report.candidates, ())

    def test_cancel_and_expansion_cap(self):
        self.import_two()
        p = self.problem()
        d = self.designer.propose(p)
        self.assertEqual(self.planner.plan(p, d, cancelled=lambda: True).status,
                         "CANCELLED")
        out = self.planner.plan(p, d, max_expansions=1)
        self.assertEqual(out.expansions, 1)
        self.assertTrue(any(code == "SEARCH_BUDGET_REACHED"
                            for _, code in out.blocked))
        with self.assertRaises(ValueError):
            self.planner.plan(p, d, max_expansions=True)

    def test_cross_problem_design_reuse_denied(self):
        self.import_two()
        a = self.problem()
        b = self.problem(id="synthetic.different")
        with self.assertRaisesRegex(ValueError, "cross-problem"):
            self.planner.plan(b, self.designer.propose(a))

    def test_corrupt_node_never_used(self):
        a, _ = self.import_two()
        (self.root / "nodes" / (a + ".axnode")).write_bytes(b"tampered")
        p = self.problem()
        with self.assertRaises(ValueError):
            self.designer.propose(p)

    def test_no_network_or_original_data_mutation(self):
        hashes = self.import_two()
        before = {(h): (self.root / "nodes" / (h + ".axnode")).read_bytes()
                  for h in hashes}
        p = self.problem()
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            self.assertEqual(self.planner.plan(p, self.designer.propose(p)).expansions, 2)
        self.assertEqual(before, {(h): (self.root / "nodes" / (h + ".axnode")).read_bytes()
                                  for h in hashes})


if __name__ == "__main__":
    unittest.main()
