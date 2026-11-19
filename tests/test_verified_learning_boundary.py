"""Immediate lane B safety checks with temporary owner keys and synthetic CSVs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.candidate_evidence_review import (
    LOCAL_RECONCILIATION_SCOPE, CandidateEvidenceReview, ReconciliationCase,
    SignedReconciliationReview, reconciliation_case_manifest_sha256,
)
from eai.candidate_review_journal import CandidateReviewJournal
from eai.contracts import ProblemSpec, canonical_bytes
from eai.experience_admission import admit_verified_episodes
from eai.logic_synthesis import LogicSynthesizer
from eai.strategy_research_ranker import rank_verified_strategies


def output(status="AGREE", *, difference=None):
    counts = dict.fromkeys(("agree", "different", "left_only", "right_only", "non_numeric"), 0)
    if difference is None:
        counts["agree"] = 1
        differences = []
    else:
        kind, key = difference
        counts[kind.lower()] = 1
        counts["agree"] = int(kind != "DIFFERENT")
        differences = [[kind, key]]
    return {"status": status, "counts": counts, "differences": differences}


class VerifiedLearningBoundaryTests(unittest.TestCase):
    def setUp(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        except ImportError:
            self.skipTest("optional Ed25519 implementation is unavailable")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.store = AXNodeStore(self.root / "nodes")
        self.addCleanup(self.store.close)
        self.owner = Ed25519PrivateKey.generate()
        self.reviewer = Ed25519PrivateKey.generate()
        self.attacker = Ed25519PrivateKey.generate()
        self.now = 1_800_000_000
        clock = patch("eai.candidate_review_journal.time", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.public_key = lambda private: private.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw)
        self.owner_public_key = self.public_key(self.owner)
        self.reviewer_public_key = self.public_key(self.reviewer)
        self.path = self.root / "unit-test-journal.sqlite"
        self.journal = CandidateReviewJournal(
            self.path, create=True, owner_public_key=self.owner_public_key)
        self.addCleanup(self.journal.close)
        self.problem = ProblemSpec.validate({
            "version": 1, "id": "test.reconcile", "goal": "Disposable reconciliation cases",
            "domain": "data", "state_refs": [], "assumptions": [], "hard_constraints": [],
            "objectives": ["accuracy", "operator_count"], "oracle": LOCAL_RECONCILIATION_SCOPE,
            "permissions": ["local.read"], "budget": {"max_steps": 4, "max_seconds": 12},
            "risk": "LOW",
        })
        self.baseline = self.compose("baseline", 3)
        self.challenger = self.compose("challenger", 2)
        self.candidates = (self.baseline, self.challenger)
        self.cases = (
            ReconciliationCase("train.agree", "TRAIN", b"key,value\na,1\n", b"key,value\na,1.0\n"),
            ReconciliationCase("train.diff", "TRAIN", b"key,value\nb,1\n", b"key,value\nb,2\n"),
            ReconciliationCase("eval.left", "HELD_OUT", b"key,value\nc,1\ng,2\n", b"key,value\nc,1\n"),
            ReconciliationCase("eval.right", "HELD_OUT", b"key,value\nd,1\n", b"key,value\nd,1\ni,2\n"),
        )
        self.outputs = {
            "train.agree": output(),
            "train.diff": output("CONFLICT", difference=("DIFFERENT", "b")),
            "eval.left": output("CONFLICT", difference=("LEFT_ONLY", "g")),
            "eval.right": output("CONFLICT", difference=("RIGHT_ONLY", "i")),
        }

    def compose(self, name, count, *, author="fixture.producer", pre=()):
        hashes = []
        for index in range(count):
            inputs = {"source": "csv_ref"}
            if index:
                inputs["prior"] = "difference_receipt"
            node = {
                "schema": "eai.axnode.v1", "id": f"{name}.{index}", "version": 1,
                "kind": "strategy", "status": "CANDIDATE",
                "signature": {"inputs": inputs, "output": "difference_receipt"},
                "pre": list(pre), "post": [], "steps": [{"skill": "csv.reconcile.v1"}],
                "capabilities": ["local.read"], "parent_hashes": hashes[-1:],
                "tests": {"unit": [], "heldout": [], "negative": []}, "evidence": [],
                "provenance": {"author": author, "source": "unit.test"},
                "budget": {"max_steps": 1, "max_seconds": 1},
            }
            hashes.append(self.store.import_node(canonical_bytes(node)))
        return LogicSynthesizer(self.store).compose(self.problem, tuple(hashes))

    def policy(self, **changes):
        document = {
            "schema": "eai.owner.verifier.policy.v1",
            "journal_id": self.journal.owner_journal_id,
            "scope": LOCAL_RECONCILIATION_SCOPE, "purpose": "LOCAL_ADVISORY_LEARNING",
            "revision": 1, "issued_at": self.now, "expires_at": self.now + 1000,
            "problem_sha256": self.problem.digest(),
            "case_manifest_sha256": reconciliation_case_manifest_sha256(self.cases),
            "baseline_sha256": self.baseline.candidate_sha256,
            "producers": {candidate.candidate_sha256: "fixture.producer"
                          for candidate in self.candidates},
            "reviewers": {"test.independent": self.reviewer_public_key.hex()},
            "revoked_key_sha256": [],
        }
        document.update(changes)
        return document

    def install(self, policy=None, *, key=None, journal=None):
        if policy is None:
            policy = self.policy()
        raw = canonical_bytes(policy)
        signer = self.owner if key is None else key
        target = self.journal if journal is None else journal
        return target.install_owner_policy(raw, signer.sign(raw))

    def review(self, candidate, nonce, *, key=None, **changes):
        policy = self.policy()
        document = {
            "schema": "eai.candidate.detached.reconciliation.v1",
            "policy_sha256": self.policy_sha, "scope": LOCAL_RECONCILIATION_SCOPE,
            "candidate_sha256": candidate.candidate_sha256,
            "problem_sha256": policy["problem_sha256"],
            "case_manifest_sha256": policy["case_manifest_sha256"],
            "verifier_id": "test.independent", "nonce": nonce,
            "issued_at": self.now, "expires_at": self.now + 30,
            "outputs": self.outputs,
        }
        document.update(changes)
        envelope = canonical_bytes(document)
        signer = self.reviewer if key is None else key
        return SignedReconciliationReview(envelope, signer.sign(envelope))

    def review_pair(self, **second_changes):
        return (self.review(self.candidates[0], "temp_case_nonce_001"),
                self.review(self.candidates[1], "temp_case_nonce_002", **second_changes))

    def rank(self, *, reviews=None, journal=None, cases=None):
        return rank_verified_strategies(
            self.store, self.problem, self.candidates,
            self.cases if cases is None else cases,
            self.review_pair() if reviews is None else reviews,
            self.journal if journal is None else journal)

    def reopen(self):
        return CandidateReviewJournal(self.path, owner_public_key=self.owner_public_key)

    def test_gated_ranking_persists_and_reopens_exact_proof_chain(self):
        self.policy_sha = self.install()
        batch = self.review_pair()
        result = self.rank(reviews=batch)
        self.assertEqual(result.status, "UPDATED_LOCAL_ADVISORY_STRATEGY")
        self.assertEqual(result.advisory_candidate_sha256, self.challenger.candidate_sha256)
        self.assertEqual(result.fallback_candidate_sha256, self.baseline.candidate_sha256)
        self.assertEqual(result.valid_until, self.now + 30)
        with self.reopen() as journal:
            entries = journal.entries()
            self.assertTrue(journal.verify_chain())
            self.assertEqual(set(e.state for e in entries), {"LOCAL_OUTCOME_REVIEWED"})
            self.assertEqual(tuple(e.entry_sha256 for e in entries), result.journal_entry_sha256)
            self.assertFalse(any(e.permits_promotion or e.changes_active_node for e in entries))
            opened = journal.current_verified_selection()
            self.assertEqual(opened.selection_sha256, result.selection_sha256)
            self.assertEqual(opened.candidate_sha256, result.advisory_candidate_sha256)
            with self.assertRaisesRegex(ValueError, "nonce already journalled"):
                self.rank(reviews=batch, journal=journal)

    def test_p2_signed_local_heldout_has_quantified_no_regression_and_cost_delta(self):
        self.policy_sha = self.install()
        result = self.rank()
        m = result.heldout_measure
        self.assertIsNotNone(m)
        self.assertEqual((m.baseline_evaluated, m.preferred_evaluated,
                          m.selected_evaluated), (2, 2, 2))
        self.assertEqual((m.baseline_errors, m.preferred_errors,
                          m.selected_errors), (0, 0, 0))
        self.assertEqual((m.preferred_extra_errors, m.selected_extra_errors), (0, 0))
        self.assertEqual(m.selected_step_delta, -1)
        self.assertEqual(m.selected_declared_seconds_delta, -1)
        self.assertTrue(m.selected_no_regression_on_pinned_cases)
        self.assertFalse(m.regression_rejected)
        self.assertFalse(m.independent_general_ood)
        self.assertFalse(m.production_accuracy_established)
        self.assertFalse(m.permits_active_promotion)
        self.assertNotIn("Disposable reconciliation", str(m))
        self.assertEqual(self.journal.current_verified_selection().candidate_sha256,
                         result.advisory_candidate_sha256)

    def test_p2_signed_heldout_regression_is_counted_but_not_selected(self):
        self.policy_sha = self.install()
        wrong = dict(self.outputs, **{"eval.left": output()})
        result = self.rank(reviews=self.review_pair(outputs=wrong))
        m = result.heldout_measure
        self.assertEqual(result.status, "ROLLBACK_HELD_OUT_REGRESSION")
        self.assertEqual((m.baseline_evaluated, m.preferred_evaluated,
                          m.selected_evaluated), (2, 2, 2))
        self.assertEqual((m.baseline_errors, m.preferred_errors,
                          m.selected_errors), (0, 1, 0))
        self.assertEqual((m.preferred_extra_errors, m.selected_extra_errors), (1, 0))
        self.assertTrue(m.regression_rejected)
        self.assertTrue(m.selected_no_regression_on_pinned_cases)
        self.assertEqual(m.selected_step_delta, 0)
        self.assertFalse(m.independent_general_ood)

    def test_p2_signed_baseline_errors_do_not_hide_recovery_or_fake_ood(self):
        self.policy_sha = self.install()
        wrong = dict(self.outputs, **{"eval.left": output()})
        reviews = (self.review(self.baseline, "temp_case_nonce_001", outputs=wrong),
                   self.review(self.challenger, "temp_case_nonce_002"))
        result = self.rank(reviews=reviews)
        m = result.heldout_measure
        self.assertEqual((m.baseline_errors, m.preferred_errors,
                          m.selected_errors), (1, 0, 0))
        self.assertEqual(m.selected_extra_errors, -1)
        self.assertFalse(m.regression_rejected)
        self.assertTrue(m.selected_no_regression_on_pinned_cases)
        self.assertFalse(m.independent_general_ood)

    def test_semantic_counterexample_does_not_replace_held_out_baseline(self):
        self.policy_sha = self.install()
        wrong = dict(self.outputs, **{"eval.left": output()})
        result = self.rank(reviews=self.review_pair(outputs=wrong))
        self.assertEqual(result.training_preference_sha256, self.challenger.candidate_sha256)
        self.assertEqual(dict(result.held_out_errors)[self.challenger.candidate_sha256], 1)
        self.assertEqual(result.status, "ROLLBACK_HELD_OUT_REGRESSION")
        self.assertEqual(result.advisory_candidate_sha256, self.baseline.candidate_sha256)
        self.assertEqual(self.journal.current_verified_selection().candidate_sha256,
                         self.baseline.candidate_sha256)

    def test_a_strictly_correct_challenger_recovers_from_unreliable_baseline(self):
        self.policy_sha = self.install()
        wrong = dict(self.outputs, **{"eval.left": output()})
        reviews = (self.review(self.baseline, "temp_case_nonce_001", outputs=wrong),
                   self.review(self.challenger, "temp_case_nonce_002"))
        result = self.rank(reviews=reviews)
        self.assertEqual(result.status, "UPDATED_LOCAL_ADVISORY_STRATEGY")
        self.assertIsNone(result.fallback_candidate_sha256)
        rolled_back = self.journal.rollback_verified_selection(
            expected_selection_sha256=result.selection_sha256)
        self.assertIsNone(rolled_back.candidate_sha256)

    def test_explicit_rollback_is_cas_bound_repeatable_and_durable(self):
        self.policy_sha = self.install()
        result = self.rank()
        with self.reopen() as journal:
            with self.assertRaisesRegex(ValueError, "head changed"):
                journal.rollback_verified_selection(expected_selection_sha256="a" * 64)
            rolled_back = journal.rollback_verified_selection(
                expected_selection_sha256=result.selection_sha256)
            self.assertEqual(rolled_back.candidate_sha256, self.baseline.candidate_sha256)
            self.assertEqual(rolled_back.preceding_selection_sha256, result.selection_sha256)
            self.assertEqual(rolled_back.journal_entry_sha256, result.journal_entry_sha256)
        with self.reopen() as journal:
            self.assertEqual(journal.current_verified_selection(), rolled_back)
            self.assertEqual(journal.rollback_verified_selection(
                expected_selection_sha256=result.selection_sha256), rolled_back)

    def test_admission_returns_checked_failure_and_cannot_be_reused_for_fit(self):
        self.policy_sha = self.install()
        wrong = dict(self.outputs, **{"train.diff": output()})
        reviews = self.review_pair(outputs=wrong)
        batch = admit_verified_episodes(
            self.store, self.problem, self.candidates, self.cases, reviews, self.journal)
        self.assertEqual(len(batch.episodes), 8)
        negative, = (e for e in batch.episodes if not e.correct)
        self.assertEqual((negative.candidate_sha256, negative.partition),
                         (self.challenger.candidate_sha256, "TRAIN"))
        self.assertTrue(self.journal.verify_chain())
        self.assertIsNone(self.journal.current_verified_selection())
        with self.assertRaisesRegex(ValueError, "nonce already journalled"):
            self.rank(reviews=reviews)

    def test_missing_owner_unknown_scope_and_caller_signing_are_denied(self):
        self.policy_sha = "0" * 64
        with self.assertRaisesRegex(PermissionError, "current signed owner approval"):
            self.rank()
        with self.assertRaisesRegex(PermissionError, "invalid owner policy signature"):
            self.install(key=self.attacker)
        for change in ({"scope": "other"}, {"purpose": "PLAYER"}):
            with self.subTest(change=change):
                with self.assertRaisesRegex(PermissionError, "does not authorize"):
                    self.install(self.policy(**change))
        with self.assertRaisesRegex(PermissionError, "distinct from candidate producers"):
            self.install(self.policy(reviewers={
                "fixture.producer": self.reviewer_public_key.hex()}))
        self.policy_sha = self.install()
        for changes in (
            {"key": self.attacker},
            {"verifier_id": "unenrolled.reviewer"},
            {"scope": "other"},
            {"case_manifest_sha256": "a" * 64},
            {"candidate_sha256": self.baseline.candidate_sha256},
            {"problem_sha256": "f" * 64},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PermissionError):
                    self.rank(reviews=self.review_pair(**changes))
        self.assertEqual(self.journal.entries(), ())

    def test_policy_revocation_survives_reopen_and_cannot_reinstall_old_key(self):
        original = self.policy()
        self.policy_sha = self.install(original)
        result = self.rank()
        revoked = hashlib.sha256(self.reviewer_public_key).hexdigest()
        with self.reopen() as journal:
            with self.assertRaisesRegex(PermissionError, "cannot revive"):
                self.install(self.policy(revision=2, reviewers={}), journal=journal)
            self.policy_sha = self.install(self.policy(revision=2, reviewers={},
                                                        revoked_key_sha256=[revoked]),
                                           journal=journal)
            self.assertIsNone(journal.current_verified_selection())
            with self.assertRaises(PermissionError):
                journal.rollback_verified_selection(
                    expected_selection_sha256=result.selection_sha256)
        with self.reopen() as journal:
            with self.assertRaisesRegex(PermissionError, "out-of-order"):
                self.install(original, journal=journal)
            with self.assertRaisesRegex(PermissionError, "revoked reviewer key"):
                self.install(self.policy(revision=3, revoked_key_sha256=[revoked]),
                             journal=journal)
            with self.assertRaisesRegex(PermissionError, "missing, revoked"):
                self.rank(journal=journal)

    def test_same_policy_identity_cannot_be_copied_to_a_new_journal(self):
        policy = self.policy()
        self.install(policy)
        with self.assertRaisesRegex(PermissionError, "owner key required"):
            CandidateReviewJournal(self.path)
        with self.assertRaisesRegex(PermissionError, "anchor mismatch"):
            CandidateReviewJournal(self.path, owner_public_key=self.public_key(self.attacker))
        with CandidateReviewJournal(
            self.root / "other.sqlite", create=True, owner_public_key=self.owner_public_key,
        ) as other:
            with self.assertRaisesRegex(PermissionError, "does not authorize this journal"):
                self.install(policy, journal=other)

    def test_same_nonce_or_interrupted_fit_rolls_back_all_writes(self):
        self.policy_sha = self.install()
        first, _ = self.review_pair()
        same_nonce = self.review(self.challenger, "temp_case_nonce_001")
        with self.assertRaisesRegex(ValueError, "nonce already journalled"):
            self.rank(reviews=(first, same_nonce))
        with patch("eai.strategy_research_ranker._fit_verified_strategy",
                   side_effect=RuntimeError("interrupted fit")):
            with self.assertRaisesRegex(RuntimeError, "interrupted fit"):
                self.rank()
        self.assertEqual(self.journal.entries(), ())
        self.assertIsNone(self.journal.current_verified_selection())
        self.assertEqual(self.rank().status, "UPDATED_LOCAL_ADVISORY_STRATEGY")

    def test_concurrent_admission_accepts_exactly_once(self):
        self.policy_sha = self.install()
        reviews = self.review_pair()
        barrier = Barrier(2)

        def update():
            with AXNodeStore(self.store.root) as store, self.reopen() as journal:
                barrier.wait(timeout=5)
                try:
                    result = rank_verified_strategies(
                        store, self.problem, self.candidates, self.cases, reviews, journal)
                except ValueError as exc:
                    return str(exc)
                return result.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(update) for _ in range(2)]
            self.assertCountEqual((task.result() for task in results), (
                "UPDATED_LOCAL_ADVISORY_STRATEGY",
                "detached verifier nonce already journalled",
            ))
        self.assertEqual(len(self.journal.entries()), 2)

    def test_expiry_during_fit_aborts_admission_and_selection(self):
        self.policy_sha = self.install()
        from eai.strategy_learner import _fit_verified_strategy

        def expired_fit(candidates, batch):
            self.now = batch.valid_until
            return _fit_verified_strategy(candidates, batch)

        with patch("eai.strategy_research_ranker._fit_verified_strategy", side_effect=expired_fit):
            with self.assertRaisesRegex(PermissionError, "expired before admission completed"):
                self.rank()
        self.assertEqual(self.journal.entries(), ())
        self.assertIsNone(self.journal.current_verified_selection())

    def test_reformatting_and_relabelling_admitted_cases_cannot_bypass_replay(self):
        self.policy_sha = self.install()
        self.rank()
        self.cases = (replace(self.cases[0], family="train.renamed",
                              left_csv=b"key,value\na,1.00\n"), *self.cases[1:])
        self.outputs["train.renamed"] = self.outputs.pop("train.agree")
        self.policy_sha = self.install(self.policy(revision=2))
        reviews = (self.review(self.baseline, "new_case_nonce_001"),
                   self.review(self.challenger, "new_case_nonce_002"))
        with self.assertRaisesRegex(ValueError, "verified episode replayed"):
            self.rank(reviews=reviews)
        self.assertEqual(len(self.journal.entries()), 2)
        self.assertIsNone(self.journal.current_verified_selection())

    def test_expired_or_future_evidence_and_backward_time_fail_closed(self):
        self.policy_sha = self.install()
        for expiry in ({"expires_at": self.now}, {"issued_at": self.now + 1},
                       {"expires_at": self.now + 301}):
            with self.subTest(expiry=expiry):
                with self.assertRaisesRegex(PermissionError, "stale"):
                    self.rank(reviews=self.review_pair(**expiry))
        result = self.rank()
        self.now += 30
        self.assertIsNone(self.journal.current_verified_selection())
        with self.assertRaises(PermissionError):
            self.journal.rollback_verified_selection(expected_selection_sha256=result.selection_sha256)
        self.now -= 1
        with self.reopen() as journal:
            with self.assertRaisesRegex(PermissionError, "clock moved backwards"):
                journal.current_verified_selection()

    def test_exact_source_and_family_no_leakage(self):
        self.policy_sha = self.install()
        changed = (replace(self.cases[0], left_csv=b"key,value\na,3\n"), *self.cases[1:])
        with self.assertRaisesRegex(PermissionError, "case source or partition"):
            self.rank(cases=changed)
        leaked = replace(self.cases[2], left_csv=b"key,value\na,1.00\n")
        with self.assertRaisesRegex(ValueError, "independent train and held-out"):
            reconciliation_case_manifest_sha256((*self.cases[:2], leaked, self.cases[3]))
        with self.assertRaisesRegex(ValueError, "unique reconciliation families"):
            reconciliation_case_manifest_sha256(
                (self.cases[0], self.cases[1], self.cases[1], self.cases[3]))
        self.assertEqual(self.journal.entries(), ())

    def test_unknown_node_semantics_self_review_and_invalid_output_fail_closed(self):
        self.challenger = self.compose("alternate", 2, pre=("unmodeled_condition",))
        self.candidates = (self.baseline, self.challenger)
        self.policy_sha = self.install()
        with self.assertRaisesRegex(PermissionError, "unsupported reconciliation node"):
            self.rank()
        self.challenger = self.compose("authored", 2, author="test.independent")
        self.candidates = (self.baseline, self.challenger)
        self.policy_sha = self.install(self.policy(revision=2))
        with self.assertRaisesRegex(PermissionError, "author cannot be"):
            self.rank()
        self.challenger = self.compose("supported", 2)
        self.candidates = (self.baseline, self.challenger)
        self.policy_sha = self.install(self.policy(revision=3))
        bad = deepcopy(self.outputs)
        bad["train.agree"]["counts"]["agree"] = True
        with self.assertRaisesRegex(ValueError, "unproven or unsupported"):
            self.rank(reviews=self.review_pair(outputs=bad))
        self.assertEqual(self.journal.entries(), ())

    def test_quarantine_clears_advisory_availability_and_permits_safe_fallback(self):
        self.policy_sha = self.install()
        result = self.rank()
        self.journal.record(CandidateEvidenceReview(
            "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT", self.problem.digest(),
            self.challenger.candidate_sha256, "a" * 64, "b" * 64, ("fixture.quarantine",), (),
        ), state="QUARANTINED")
        self.assertIsNone(self.journal.current_verified_selection())
        self.assertEqual(self.journal.rollback_verified_selection(
            expected_selection_sha256=result.selection_sha256).candidate_sha256,
            self.baseline.candidate_sha256)

    def test_tampered_replay_index_fails_reopen(self):
        self.policy_sha = self.install()
        self.rank()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM verified_replays WHERE sequence=1")
        with self.assertRaisesRegex(ValueError, "replay fence integrity"):
            self.reopen()

    def test_deleted_revocation_cannot_fall_back_to_previous_owner_policy(self):
        self.install()
        revoked = hashlib.sha256(self.reviewer_public_key).hexdigest()
        self.install(self.policy(revision=2, reviewers={}, revoked_key_sha256=[revoked]))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM owner_policy WHERE revision=2")
        with self.assertRaisesRegex(ValueError, "revision history diverged"):
            self.reopen()


if __name__ == "__main__":
    unittest.main()
