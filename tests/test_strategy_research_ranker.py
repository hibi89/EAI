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
from eai.synthetic_curriculum import (generate_synthetic_curriculum,
                                      generate_synthetic_transfer_families)
from eai.synthetic_scenario_transfer import evaluate_synthetic_scenario_transfer
from eai.strategy_learner import advance_bounded_research_prior


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
        self.assertIs(type(outcome.ranked[0].measured_synthetic_cpu_ms), int)
        self.assertGreaterEqual(outcome.ranked[0].measured_synthetic_cpu_ms, 0)
        self.assertFalse(outcome.learner_trained)
        self.assertFalse(outcome.ranked[0].trusted_for_learning)
        self.assertFalse(outcome.permits_promotion)
        self.assertFalse(outcome.permits_real_execution)
        self.assertEqual(outcome.verified_uplift, "NOT_MEASURED")

    def test_same_source_same_synthetic_rank_deterministic(self):
        with patch("eai.strategy_research_ranker.perf_counter_ns",
                   side_effect=(0, 100_000_000, 0, 100_000_000)), patch(
                       "eai.strategy_research_ranker.process_time_ns",
                       side_effect=(0, 37_000_000, 0, 37_000_000)):
            first, second = self.rank(), self.rank()
        self.assertEqual(first, second)
        self.assertEqual(first.ranked[0].measured_synthetic_cpu_ms, 37)


    def test_p2_new_scenario_classes_are_disjoint_and_quantitatively_compared(self):
        from eai.synthetic_holdout import _fixture_hash
        probes = generate_synthetic_transfer_families(0)
        self.assertEqual(len(probes), 2)
        self.assertEqual(len({_fixture_hash(v) for v in
                              self.curriculum.train + self.curriculum.heldout + probes}), 6)
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            proof = evaluate_synthetic_scenario_transfer(
                self.store, self.problem, self.candidate, self.curriculum)
        self.assertEqual(proof.status, "SYNTHETIC_SCENARIO_TRANSFER_MATCH_UNVERIFIED")
        self.assertEqual((proof.challenge_families, proof.b0_checked,
                          proof.b1_checked, proof.b1_unmatched), (2, 2, 2, 0))
        self.assertFalse(proof.independently_verified_real_world)
        self.assertFalse(proof.permits_promotion)
        self.assertFalse(proof.permits_learning)

    def test_p2_research_prior_updates_only_after_scenario_transfer(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            first = advance_bounded_research_prior(
                self.store, self.problem, (self.candidate,), self.curriculum)
        self.assertTrue(first.accepted)
        self.assertEqual(first.synthetic_scenario_families_checked, 2)
        self.assertEqual(first.synthetic_scenario_candidate_matches, 2)
        self.assertEqual(first.prior.observed_synthetic_families, 4)
        self.assertFalse(first.prior.trusted_training_permitted)
        self.assertFalse(first.prior.active_promotion_permitted)
        self.assertFalse(first.prior.independent_real_world_truth)
        again = advance_bounded_research_prior(
            self.store, self.problem, (self.candidate,), self.curriculum, first.prior)
        self.assertFalse(again.accepted)
        self.assertIs(again.prior, first.prior)
        self.assertEqual(again.status, "HOLD_REPLAYED_OR_EXHAUSTED_SYNTHETIC_FAMILY")

    def test_p2_scenario_counterexample_preserves_prior_and_denies_learning(self):
        from eai.synthetic_scenario_transfer import SyntheticScenarioTransfer
        from dataclasses import replace as dataclass_replace
        ok = advance_bounded_research_prior(
            self.store, self.problem, (self.candidate,), self.curriculum)
        self.assertTrue(ok.accepted)
        next_curriculum = generate_synthetic_curriculum(1)
        rejected = SyntheticScenarioTransfer(
            self.candidate.candidate_sha256,
            "HOLD_SYNTHETIC_SCENARIO_COUNTEREXAMPLE", 2, 2, 1, 1,
            ("negative_signed_decimals", "multiple_key_and_value_changes"))
        with patch("eai.synthetic_scenario_transfer.evaluate_synthetic_scenario_transfer",
                   return_value=rejected):
            denied = advance_bounded_research_prior(
                self.store, self.problem, (self.candidate,),
                next_curriculum, ok.prior)
        self.assertFalse(denied.accepted)
        self.assertIs(denied.prior, ok.prior)
        self.assertTrue(denied.synthetic_scenario_regression_rejected)
        self.assertEqual(denied.synthetic_scenario_candidate_matches, 1)
        self.assertEqual(denied.reason_codes,
                         ("SYNTHETIC_SCENARIO_TRANSFER_COUNTEREXAMPLE",))
        self.assertFalse(denied.model_can_execute)
        self.assertFalse(denied.real_world_uplift_verified)

    def test_p2_forged_success_transfer_provenance_never_updates_prior(self):
        from eai.synthetic_scenario_transfer import SyntheticScenarioTransfer
        first = advance_bounded_research_prior(
            self.store, self.problem, (self.candidate,), self.curriculum)
        self.assertTrue(first.accepted)
        new_curriculum = generate_synthetic_curriculum(1)
        real = evaluate_synthetic_scenario_transfer(
            self.store, self.problem, self.candidate, new_curriculum)
        self.assertEqual(real.status, "SYNTHETIC_SCENARIO_TRANSFER_MATCH_UNVERIFIED")
        forged_reports = (
            replace(real, candidate_sha256="f" * 64),
            replace(real, challenge_families=1, b0_checked=1, b1_checked=1),
            replace(real, b1_unmatched=1),
            replace(real, scenario_types=("renamed_seed", "renamed_seed")),
            replace(real, semantic_scope="REAL_WORLD_OOD"),
            replace(real, independently_verified_real_world=True),
            "not-a-report",
        )
        for forged in forged_reports:
            with self.subTest(forged=repr(forged)), patch(
                    "eai.synthetic_scenario_transfer.evaluate_synthetic_scenario_transfer",
                    return_value=forged):
                denied = advance_bounded_research_prior(
                    self.store, self.problem, (self.candidate,),
                    new_curriculum, first.prior)
                self.assertFalse(denied.accepted)
                self.assertIs(denied.prior, first.prior)
                self.assertTrue(denied.synthetic_scenario_regression_rejected)
                self.assertFalse(denied.real_world_uplift_verified)
                self.assertFalse(denied.model_can_execute)

    def test_p2_forged_synthetic_transfer_fixture_never_enters_baseline(self):
        for seed in (True, -1, 10001, "0"):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                generate_synthetic_transfer_families(seed)
        forged = replace(self.curriculum, heldout=self.curriculum.train)
        with self.assertRaisesRegex(ValueError, "verified local synthetic curriculum"):
            evaluate_synthetic_scenario_transfer(
                self.store, self.problem, self.candidate, forged)

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
