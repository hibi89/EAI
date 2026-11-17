"""C15 isolated journal: no ACTIVE mutation, no bypass, tamper detection."""
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from eai.candidate_evidence_review import CandidateEvidenceReview
from eai.candidate_review_journal import CandidateReviewJournal


class CandidateReviewJournalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / "review.sqlite"
        self.review = CandidateEvidenceReview(
            "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED", "1" * 64, "2" * 64,
            "3" * 64, "4" * 64, (), ())

    def test_append_reopen_and_hash_chain(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            one = journal.record(self.review, state="REVIEW_HOLD",
                                 previous_active_sha256="a" * 64)
            two = journal.record(self.review, state="QUARANTINED",
                                 previous_active_sha256="a" * 64)
            three = journal.record(self.review, state="WITHDRAWN_FROM_REVIEW",
                                   previous_active_sha256="a" * 64)
            self.assertEqual([one.sequence, two.sequence, three.sequence],
                             [1, 2, 3])
            self.assertEqual(two.previous_entry_sha256, one.entry_sha256)
            self.assertFalse(three.changes_active_node)
            self.assertFalse(three.permits_promotion)
            self.assertTrue(journal.verify_chain())
        with CandidateReviewJournal(self.path) as reopened:
            self.assertEqual(len(reopened.entries()), 3)
            self.assertEqual(reopened.entries()[0].previous_active_sha256,
                             "a" * 64)

    def test_auto_active_promotion_is_not_a_supported_state(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            for state in ("ACTIVE", "VERIFIED", "PROMOTE", "APPROVED"):
                with self.subTest(state=state), self.assertRaises(ValueError):
                    journal.record(self.review, state=state)
            self.assertEqual(journal.entries(), ())

    def test_forged_learning_and_execution_authority_denied(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            for fake in (
                replace(self.review, permits_promotion=True),
                replace(self.review, permits_learning=True),
                replace(self.review, permits_real_execution=True),
            ):
                with self.assertRaisesRegex(ValueError, "authority denied"):
                    journal.record(fake, state="REVIEW_HOLD")
            self.assertEqual(journal.entries(), ())

    def test_withdrawal_without_prior_review_is_denied(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            with self.assertRaisesRegex(ValueError, "not previously reviewed"):
                journal.record(self.review, state="WITHDRAWN_FROM_REVIEW")

    def test_tampered_hash_chain_fails_reopen(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            journal.record(self.review, state="QUARANTINED")
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE entries SET entry_sha256=? WHERE sequence=1",
                       ("f" * 64,))
        with self.assertRaisesRegex(ValueError, "chain integrity"):
            CandidateReviewJournal(self.path)

    def test_existing_file_not_overwritten_on_create(self):
        self.path.write_bytes(b"original")
        with self.assertRaises(ValueError):
            CandidateReviewJournal(self.path, create=True)
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_symlinked_journal_rejected(self):
        source = self.root / "other.sqlite"
        source.write_bytes(b"original")
        try:
            self.path.symlink_to(source)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unsupported")
        with self.assertRaises(ValueError):
            CandidateReviewJournal(self.path)
        self.assertEqual(source.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
