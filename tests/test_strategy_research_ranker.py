"""C17 advisory strategy ranking reruns real synthetic B0/B1 CPU verification."""
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
from eai.strategy_research_ranker import rank_synthetic_strategy_previews
from eai.synthetic_curriculum import generate_synthetic_curriculum


class StrategyResearchRankerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = AXNodeStore(Path(tmp.name) / "synthetic")
        self.addCleanup(self.store.close)
        first = self.store.import_node(json.dumps(self.node("strategy.first", [])))
        second = self.store.import_node(json.dumps(
            self.node("strategy.second", [first])))
        self.problem = ProblemSpec.validate({
            "version": 1, "id": "synthetic.ranker", "goal": "PRIVATE goal",
            "domain": "data", "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["accuracy"],
            "oracle": "synthetic.only", "permissions": ["local.read"],
            "budget": {"max_steps": 5, "max_seconds": 100},
            "risk": "LOW",
        })
        self.candidate = LogicSynthesizer(self.store).compose(
            self.problem, (first, second))
        self.curriculum = generate_synthetic_curriculum(0)

    @staticmethod
    def node(name, parents):
        return {
            "schema": "eai.axnode.v1", "id": name, "version": 1,
            "kind": "strategy", "status": "CANDIDATE",
            "signature": {
                "inputs": {"csv": "csv_ref", "prior": "difference_receipt"},
                "output": "difference_receipt"},
            "pre": ["synthetic_only"], "post": ["check_independently"],
            "steps": [{"skill": "csv.reconcile.v1"}],
            "capabilities": ["local.read"], "parent_hashes": parents,
            "tests": {"unit": [], "heldout": [], "negative": []},
            "evidence": [],
            "provenance": {"author": "local_fixture",
                           "source": "synthetic_only"},
            "budget": {"max_steps": 2, "max_seconds": 20},
        }

    def rank(self, *, candidates=None, curriculum=None, problem=None):
        return rank_synthetic_strategy_previews(
            self.store, self.problem if problem is None else problem,
            (self.candidate,) if candidates is None else candidates,
            self.curriculum if curriculum is None else curriculum)

    def test_synthetic_cpu_recheck_ranks_without_training_or_execution(self):
        with patch.object(socket, "socket",
                          side_effect=AssertionError("network forbidden")):
            outcome = self.rank()
        self.assertEqual(outcome.disposition,
                         "SYNTHETIC_COST_ORDER_ONLY_NOT_LEARNING")
        self.assertEqual(len(outcome.ranked), 1)
        self.assertEqual(outcome.ranked[0].compared_train, 2)
        self.assertEqual(outcome.ranked[0].compared_heldout, 2)
        self.assertFalse(outcome.learner_trained)
        self.assertFalse(outcome.ranked[0].trusted_for_learning)
        self.assertFalse(outcome.permits_promotion)
        self.assertFalse(outcome.permits_real_execution)
        self.assertEqual(outcome.verified_uplift, "NOT_MEASURED")

    def test_same_source_same_synthetic_rank_deterministic(self):
        self.assertEqual(self.rank(), self.rank())

    def test_forged_candidate_digest_cannot_be_ranked(self):
        bad = replace(self.candidate, candidate_sha256="f" * 64)
        report = self.rank(candidates=(bad,))
        self.assertEqual(report.disposition,
                         "HOLD_NO_RECHECKED_SYNTHETIC_STRATEGY")
        self.assertEqual(report.ranked, ())
        self.assertIn("CANDIDATE_STRUCTURE_OR_HASH_CHANGED",
                      report.held[0][1])

    def test_cross_problem_candidate_reuse_refused(self):
        other = replace(self.problem, goal="different private goal")
        report = self.rank(problem=other)
        self.assertEqual(report.ranked, ())
        self.assertFalse(report.learner_trained)

    def test_forged_split_or_manifest_refused_before_oracle(self):
        bad = replace(self.curriculum,
                      heldout=self.curriculum.train)
        with self.assertRaisesRegex(ValueError, "forged or cross-split"):
            self.rank(curriculum=bad)

    def test_duplicate_candidate_inventory_denied(self):
        with self.assertRaisesRegex(ValueError, "repeated candidate"):
            self.rank(candidates=(self.candidate, self.candidate))

    def test_candidate_composition_rejects_unsafe_node(self):
        bad = replace(self.candidate, node_hashes=("f" * 64, "e" * 64))
        result = self.rank(candidates=(bad,))
        self.assertEqual(result.ranked, ())
        self.assertFalse(result.permits_promotion)

    def test_untrusted_benchmark_output_cannot_mint_training_signal(self):
        from eai.synthetic_candidate_benchmark import SyntheticB1Benchmark
        forged = SyntheticB1Benchmark(
            "B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED", 2, 2,
            2, 2, 2, 2, self.candidate.candidate_sha256,
            external_truth_verified=True, permission_to_learn=True)
        with patch(
                "eai.strategy_research_ranker.benchmark_synthetic_candidate",
                return_value=forged):
            result = self.rank()
        self.assertEqual(result.ranked, ())
        self.assertEqual(result.disposition,
                         "HOLD_NO_RECHECKED_SYNTHETIC_STRATEGY")
