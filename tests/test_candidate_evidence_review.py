"""C14/C16 exact synthetic receipt binding and no-learning guarantees."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.contracts import ProblemSpec, canonical_bytes
from eai.logic_oracle import SyntheticComparison
from eai.logic_synthesis import LogicSynthesizer
from eai.synthetic_candidate_interpreter import interpret_synthetic_candidate
from eai.synthetic_candidate_verifier import verify_synthetic_interpretation
from eai.candidate_evidence_review import (
    intake_candidate_receipt_for_review, review_candidate_evidence,
)
from eai.candidate_review_journal import CandidateReviewJournal


class CandidateEvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = AXNodeStore(self.root / "nodes")
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

    def signed_review(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        except ImportError:
            self.skipTest("optional Ed25519 implementation is unavailable")
        review = self.review()
        key = Ed25519PrivateKey.generate()
        public_key = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        envelope = canonical_bytes({
            "schema": "eai.candidate.detached.review.v1",
            "candidate_sha256": review.candidate_sha256,
            "review_sha256": review.review_sha256,
            "fixture_sha256": review.fixture_sha256,
            "problem_sha256": review.problem_sha256,
            "verifier_id": "synthetic.test.verifier",
            "disposition": "REVIEW_METADATA_ONLY",
            "nonce": "test_signature_nonce_01",
        })
        return dict(detached_envelope=envelope, detached_signature=key.sign(envelope),
                    pinned_public_key=public_key,
                    pinned_key_sha256=hashlib.sha256(public_key).hexdigest())

    def intake(self, journal, **options):
        return intake_candidate_receipt_for_review(
            self.store, self.problem, self.candidate, self.fixtures,
            self.witness, self.receipt, journal, **options)

    def test_signed_receipt_is_durable_but_carries_no_authority_and_cannot_replay(self):
        signed = self.signed_review()
        path = self.root / "journal.sqlite"
        with CandidateReviewJournal(path, create=True) as journal:
            preview = self.intake(journal, **signed)
            self.assertEqual(journal.entries(), ())
            result = self.intake(journal, record_locally=True, **signed)
            self.assertEqual(result.detached_binding_sha256, preview.detached_binding_sha256)
            self.assertEqual(len(result.detached_binding_sha256), 64)
            self.assertFalse(result.source_authenticated)
            self.assertFalse(result.verified_real_world)
            self.assertFalse(result.permits_learning)
            self.assertFalse(result.permits_execution)
            self.assertFalse(result.permits_promotion)
        with CandidateReviewJournal(path) as journal:
            entry = journal.entry_at(1)
            self.assertEqual(entry.entry_sha256, result.journal_entry_sha256)
            self.assertEqual(entry.evidence_sha256, result.independent_review_sha256)
            self.assertEqual(entry.detached_binding_sha256, result.detached_binding_sha256)
            with self.assertRaisesRegex(ValueError, "nonce already journalled"):
                self.intake(journal, record_locally=True, **signed)
            self.assertEqual(journal.entries(), (entry,))

    def test_invalid_signature_and_wrong_evidence_are_rejected_before_journal_write(self):
        signed = self.signed_review()
        with CandidateReviewJournal(self.root / "journal.sqlite", create=True) as journal:
            bad_signature = dict(signed, detached_signature=b"\x00" * 64)
            self.assertEqual(self.intake(journal, record_locally=True,
                                         **bad_signature).status,
                             "HOLD_UNAUTHENTICATED_DETACHED_REVIEW")
            envelope = json.loads(signed["detached_envelope"])
            envelope["fixture_sha256"] = "0" * 64
            wrong_evidence = dict(signed, detached_envelope=canonical_bytes(envelope))
            with self.assertRaisesRegex(ValueError, "canonical exact evidence"):
                self.intake(journal, record_locally=True, **wrong_evidence)
            self.assertEqual(journal.entries(), ())

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
