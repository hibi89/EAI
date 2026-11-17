
"""Synthetic review-only durable replay fence; no training/execution permission."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from eai.episode_replay_fence import EpisodeReplayFence
from eai.episode_replay_dedup import EpisodeBatchReview


class EpisodeReplayFenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.file = self.base / "review.sqlite"
        self.review = EpisodeBatchReview(
            "SYNTHETIC_EPISODE_MANUAL_REVIEW_ONLY",
            "a" * 64, ("b" * 64, "c" * 64), (), ())

    def test_creation_reopen_readonly(self):
        with EpisodeReplayFence(self.file, create=True) as fence:
            recorded = fence.record(self.review)
            self.assertEqual(recorded.recorded_count, 2)
            self.assertFalse(recorded.grants_learning)
            self.assertFalse(recorded.grants_execution)
        with EpisodeReplayFence(self.file) as fence:
            self.assertTrue(fence.contains("b" * 64))
            with self.assertRaises(PermissionError):
                fence.record(self.review)

    def test_duplicate_rejected_atomically_on_append(self):
        with EpisodeReplayFence(self.file, create=True) as fence:
            fence.record(self.review)
        with EpisodeReplayFence(self.file, append_existing=True) as fence:
            forged = replace(self.review, reviewed_fingerprints=(
                "d" * 64, "b" * 64))
            with self.assertRaises(ValueError):
                fence.record(forged)
            self.assertFalse(fence.contains("d" * 64))
            self.assertTrue(fence.contains("b" * 64))

    def test_held_or_authorizing_review_is_forbidden(self):
        with EpisodeReplayFence(self.file, create=True) as fence:
            for bad in (replace(self.review, admits_training=True),
                        replace(self.review, grants_execution=True),
                        replace(self.review, reasons=("DUPLICATE",)),
                        replace(self.review, status="HOLD")):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    fence.record(bad)
            self.assertFalse(fence.contains("b" * 64))

    def test_existing_user_file_not_overwritten(self):
        self.file.write_bytes(b"original")
        with self.assertRaises(ValueError):
            EpisodeReplayFence(self.file, create=True)
        self.assertEqual(self.file.read_bytes(), b"original")

    def test_symlink_rejected(self):
        original = self.base / "original"
        original.write_bytes(b"untouched")
        try:
            self.file.symlink_to(original)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unsupported")
        with self.assertRaises(ValueError):
            EpisodeReplayFence(self.file, create=True)
        self.assertEqual(original.read_bytes(), b"untouched")

    def test_wrong_schema_version_fails(self):
        with EpisodeReplayFence(self.file, create=True):
            pass
        with closing(sqlite3.connect(self.file)) as db:
            db.execute("PRAGMA user_version=2")
        with self.assertRaises(ValueError):
            EpisodeReplayFence(self.file, append_existing=True)

    def test_invalid_and_duplicate_fingerprints_denied(self):
        with EpisodeReplayFence(self.file, create=True) as fence:
            for hashes in (("bad",), ("b" * 64, "b" * 64), ()):
                with self.subTest(hashes=hashes), self.assertRaises(ValueError):
                    fence.record(replace(self.review,
                                         reviewed_fingerprints=hashes))
