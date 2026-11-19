"""C15 isolated journal: no ACTIVE mutation, no bypass, tamper detection."""
from contextlib import closing
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
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE entries SET entry_sha256=? WHERE sequence=1",
                       ("f" * 64,))
        with self.assertRaisesRegex(ValueError, "chain integrity"):
            CandidateReviewJournal(self.path)

    def test_signed_binding_readback_is_by_sequence_and_detects_tampering(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            signed = journal.record(self.review, state="REVIEW_HOLD",
                                    detached_binding_sha256="a" * 64,
                                    detached_nonce_sha256="b" * 64)
            journal.record(self.review, state="QUARANTINED")
            self.assertEqual(journal.entry_at(signed.sequence), signed)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE entries SET detached_binding_sha256=? WHERE sequence=1",
                       ("c" * 64,))
        with self.assertRaisesRegex(ValueError, "chain integrity"):
            CandidateReviewJournal(self.path)

    def test_v1_can_append_unsigned_and_cannot_be_migrated_by_signed_write(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE entries (
                    sequence INTEGER PRIMARY KEY, candidate_sha256 TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL, state TEXT NOT NULL,
                    previous_active_sha256 TEXT, previous_entry_sha256 TEXT NOT NULL,
                    entry_sha256 TEXT NOT NULL UNIQUE
                );
                PRAGMA user_version=1;
            """)
        with CandidateReviewJournal(self.path) as legacy:
            self.assertFalse(legacy.supports_detached_bindings)
            first = legacy.record(self.review, state="REVIEW_HOLD")
            with self.assertRaisesRegex(ValueError, "new journal"):
                legacy.record(self.review, state="QUARANTINED",
                              detached_binding_sha256="a" * 64,
                              detached_nonce_sha256="b" * 64)
            self.assertEqual(legacy.entries(), (first,))
            self.assertEqual(legacy.db.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_quarantine_may_not_self_downgrade_to_hold(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            journal.record(self.review, state="QUARANTINED")
            with self.assertRaisesRegex(ValueError, "cannot self-reinstate"):
                journal.record(self.review, state="REVIEW_HOLD")
            latest = journal.latest_for(self.review.candidate_sha256)
            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest.state, "QUARANTINED")

    def test_withdrawn_review_is_terminal_even_if_user_supplies_new_claim(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            journal.record(self.review, state="REVIEW_HOLD")
            journal.record(self.review, state="WITHDRAWN_FROM_REVIEW")
            with self.assertRaisesRegex(ValueError, "cannot be resurrected"):
                journal.record(self.review, state="QUARANTINED")
            self.assertEqual(len(journal.entries()), 2)

    def test_duplicate_review_event_does_not_inflate_history(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            journal.record(self.review, state="REVIEW_HOLD")
            with self.assertRaisesRegex(ValueError, "duplicate journal event"):
                journal.record(self.review, state="REVIEW_HOLD")
            self.assertEqual(len(journal.entries()), 1)

    def test_changed_active_pointer_metadata_requires_separate_review(self):
        with CandidateReviewJournal(self.path, create=True) as journal:
            journal.record(self.review, state="REVIEW_HOLD",
                           previous_active_sha256="a" * 64)
            with self.assertRaisesRegex(ValueError, "ACTIVE pointer evidence changed"):
                journal.record(self.review, state="QUARANTINED",
                               previous_active_sha256="b" * 64)
            latest = journal.latest_for(self.review.candidate_sha256)
            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest.previous_active_sha256, "a" * 64)

    def test_untrusted_receipt_cannot_enter_review_hold(self):
        bad = replace(self.review,
                      status="QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT",
                      reason_codes=("FORGED_RECEIPT_AUTHORITY",))
        with CandidateReviewJournal(self.path, create=True) as journal:
            with self.assertRaisesRegex(ValueError, "untrusted review"):
                journal.record(bad, state="REVIEW_HOLD")
            journal.record(bad, state="QUARANTINED")
            latest = journal.latest_for(bad.candidate_sha256)
            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest.state, "QUARANTINED")

    def test_existing_file_not_overwritten_on_create(self):
        self.path.write_bytes(b"original")
        with self.assertRaises(ValueError):
            CandidateReviewJournal(self.path, create=True)
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_unrelated_database_is_rejected_without_changing_journal_mode(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE original (id INTEGER)")
            db.execute("INSERT INTO original VALUES (1)")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "unknown journal version"):
            CandidateReviewJournal(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.path.with_name(self.path.name + "-wal").exists())

    def test_quarantined_review_never_mutates_original_active_pointer(self):
        active = self.root / "active-pointer.sha256"
        active.write_text("a" * 64, encoding="ascii")
        with CandidateReviewJournal(self.path, create=True) as journal:
            receipt = journal.record(
                self.review, state="QUARANTINED",
                previous_active_sha256="a" * 64)
            self.assertFalse(receipt.changes_active_node)
        self.assertEqual(active.read_text(encoding="ascii"), "a" * 64)

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
