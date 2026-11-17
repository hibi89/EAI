"""C15 review journal != signed consent or ACTIVE promotion."""
import tempfile
from pathlib import Path
from unittest import TestCase

from eai.candidate_evidence_review import CandidateEvidenceReview
from eai.candidate_review_journal import CandidateReviewJournal
from eai.candidate_activation_preflight import inspect_activation_preflight


class CandidateActivationPreflightTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "review.sqlite"
        self.review = CandidateEvidenceReview(
            "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED",
            "1" * 64, "2" * 64, "3" * 64, "4" * 64,
            (), ())
        self.journal = CandidateReviewJournal(self.path, create=True)
        self.addCleanup(self.journal.close)

    def test_absent_review_cannot_activate(self):
        check = inspect_activation_preflight(self.journal, self.review)
        self.assertEqual(check.disposition, "ACTIVATION_FORBIDDEN")
        self.assertIn("NO_JOURNALLED_CANDIDATE_REVIEW", check.reasons)
        self.assertFalse(check.may_activate)

    def test_valid_hold_is_still_missing_owner_and_independent_proof(self):
        self.journal.record(self.review, state="REVIEW_HOLD")
        check = inspect_activation_preflight(self.journal, self.review)
        self.assertEqual(check.current_review_state, "REVIEW_HOLD")
        self.assertIn("TRUSTED_INDEPENDENT_PROOF_MISSING", check.reasons)
        self.assertIn("OWNER_EXACT_SCOPE_APPROVAL_MISSING", check.reasons)
        self.assertFalse(check.may_modify_original)

    def test_prior_active_pointer_change_prevents_release(self):
        self.journal.record(self.review, state="REVIEW_HOLD",
                            previous_active_sha256="a" * 64)
        check = inspect_activation_preflight(
            self.journal, self.review, current_active_sha256="b" * 64)
        self.assertIn("ACTIVE_POINTER_CHANGED", check.reasons)
        self.assertFalse(check.may_activate)

    def test_quarantined_candidate_stays_nonactivatable(self):
        self.journal.record(self.review, state="QUARANTINED")
        check = inspect_activation_preflight(self.journal, self.review)
        self.assertIn("NOT_IN_REVIEW_HOLD", check.reasons)
        self.assertFalse(check.may_activate)
