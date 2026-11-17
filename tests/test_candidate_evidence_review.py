"""C14/C16 exact synthetic receipt binding and no-learning guarantees."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.contracts import ProblemSpec
from eai.logic_oracle import SyntheticComparison
from eai.logic_synthesis import LogicSynthesizer
from eai.synthetic_candidate_interpreter import interpret_synthetic_candidate
from eai.synthetic_candidate_verifier import verify_synthetic_interpretation
from eai.candidate_evidence_review import review_candidate_evidence


class CandidateEvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = AXNodeStore(Path(tmp.name) / "nodes")
        self.addCleanup(self.store.close)
        def node(name, parents):
            return {
                "schema": "eai.axnode.v1", "id": name, "version": 1,
                "kind": "strategy", "status": "CANDIDATE",
                "signature": {"inputs": {"source": "csv_ref",
                                          "previous": "difference_receipt"},
                              "output": "difference_receipt"},
                "pre": ["authorized_synthetic_only"],
                "post": ["independent_reference_required"],
                "steps": [{"skill": "csv.reconcile.v1"}],
                "capabilities": ["local.read"], "parent_hashes": parents,
                "tests": {"unit": [], "heldout": [], "negative": []},
                "evidence": [],
                "provenance": {"author": "eai_synthetic", "source": "local_only"},
                "budget": {"max_steps": 2, "max_seconds": 10},
            }
        a = self.store.import_node(json.dumps(node("data.one", [])))
        b = self.store.import_node(json.dumps(node("data.two", [a])))
        self.problem = ProblemSpec.validate({
            "version": 1, "id": "synthetic.receipt",
            "goal": "PRIVATE not serialized in provenance review",
            "domain": "data", "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["safety"],
            "oracle": "synthetic.reference", "permissions": ["local.read"],
            "budget": {"max_steps": 5, "max_seconds": 60}, "risk": "LOW",
        })
        self.candidate = LogicSynthesizer(self.store).compose(
            self.problem, (a, b))
        self.fixtures = (
            SyntheticComparison("family.equal", (("a", "1"),),
                                (("a", "1.0"),), ()),
            SyntheticComparison("family.diff", (("a", "1"),),
                                (("a", "2"),), ("a",)),
        )
        self.witness = interpret_synthetic_candidate(
            self.store, self.problem, self.candidate, self.fixtures)
        self.receipt = verify_synthetic_interpretation(
            self.store, self.problem, self.candidate,
            self.fixtures, self.witness)

    def review(self, **changes):
        return review_candidate_evidence(
            self.store, self.problem, self.candidate,
            changes.get("fixtures", self.fixtures),
            changes.get("witness", self.witness),
            changes.get("claimed", self.receipt))

    def test_independent_replay_matches_but_cannot_promote_or_train(self):
        result = self.review()
        self.assertEqual(result.status, "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED")
        self.assertFalse(result.permits_promotion)
        self.assertFalse(result.permits_learning)
        self.assertFalse(result.permits_real_execution)
        self.assertEqual(len(result.review_sha256), 64)
        self.assertNotIn("PRIVATE", str(result))
        self.assertEqual(result, self.review())

    def test_fake_receipt_authority_is_quarantined(self):
        forged = replace(self.receipt, permits_promotion=True,
                         real_world_verified=True)
        result = self.review(claimed=forged)
        self.assertEqual(result.status, "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT")
        self.assertIn("FORGED_RECEIPT_AUTHORITY", result.reason_codes)

    def test_changed_problem_receipt_cannot_be_reused(self):
        forged = replace(self.receipt, problem_sha256="0" * 64)
        result = self.review(claimed=forged)
        self.assertIn(
            "CLAIMED_RECEIPT_DIFFERS_FROM_INDEPENDENT_RECOMPUTATION",
            result.reason_codes)

    def test_changed_fixture_values_bind_new_review_hash(self):
        changed = (
            self.fixtures[0],
            replace(self.fixtures[1], left=(("a", "4"),),
                    right=(("a", "5"),)),
        )
        result = self.review(fixtures=changed)
        self.assertEqual(result.status, "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED")
        self.assertNotEqual(result.fixture_sha256, self.review().fixture_sha256)
        self.assertNotEqual(result.review_sha256, self.review().review_sha256)

    def test_changed_fixture_effect_quarantines_replayed_receipt(self):
        changed = (
            self.fixtures[0],
            replace(self.fixtures[1], right=(("a", "1"),)),
        )
        result = self.review(fixtures=changed)
        self.assertEqual(result.status, "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT")
        self.assertIn("INDEPENDENT_CPU_OR_STRUCTURE_DID_NOT_MATCH",
                      result.reason_codes)

    def test_replay_mismatch_quarantines_even_valid_cpu_receipt(self):
        fake_replay = replace(self.witness, witness_sha256="f" * 64)
        with patch("eai.candidate_evidence_review.interpret_synthetic_candidate",
                   return_value=fake_replay):
            result = self.review()
        self.assertEqual(result.status, "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT")
        self.assertIn("EXECUTION_WITNESS_NOT_REPRODUCIBLE",
                      result.reason_codes)
        self.assertFalse(result.permits_promotion)

    def test_missing_independent_replay_cannot_certify_a_receipt(self):
        with patch("eai.candidate_evidence_review.interpret_synthetic_candidate",
                   side_effect=ValueError("unsupported candidate")):
            result = self.review()
        self.assertIn("INDEPENDENT_SYNTHETIC_REPLAY_REJECTED",
                      result.reason_codes)
        self.assertFalse(result.permits_learning)

    def test_corrupted_execution_digest_cannot_be_reviewed(self):
        corrupted = replace(self.witness, witness_sha256="0" * 64)
        result = self.review(witness=corrupted)
        self.assertEqual(result.status, "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT")
        self.assertFalse(result.permits_promotion)


if __name__ == "__main__":
    unittest.main()
