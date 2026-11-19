"""Immediate AXNODE write-epoch safety checks on disposable synthetic stores."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from eai import axnode_restore, sidecar_coherence_review
from eai.axnode_memory import AXNodeMemory
from eai.axnode_recovery import review_isolated_restore_commit_or_hold
from eai.axnode_restore import (
    IsolatedRestoreRequest, create_isolated_restore_ledger,
    recover_isolated_restore, rollback_isolated_restore,
)
from eai.axnode_sidecar_backup import create_sidecar_bundle, restore_sidecar_bundle
from eai.axnode_store import AXNodeStore
from eai.evidence_ledger import EvidenceLedger
from eai.sidecar_coherence_review import inspect_isolated_epoch_boundary


_INTERRUPTED = 73
_CRASH_WORKER = """
from contextlib import contextmanager
import os
from pathlib import Path
import sys
from unittest.mock import patch

from eai import axnode_restore as restore
from eai.axnode_recovery import review_isolated_restore_commit_or_hold
from eai.axnode_store import AXNodeStore

when, action, source, archive, staged, root, operation_id, rev, checkpoint = sys.argv[1:]
journal = Path(root) / "epoch.sqlite-journal"

append = restore._append_transition
def interrupt_before_commit(db, *args, **kwargs):
    db.execute("PRAGMA cache_size=2")
    append(db, *args, **kwargs)
    assert journal.exists()
    os._exit(73)

transaction = restore._recovery_transaction
@contextmanager
def interrupt_after_commit(*args, **kwargs):
    with transaction(*args, **kwargs) as db:
        yield db
    assert not journal.exists()
    os._exit(73)

if when == "before":
    interruption = patch.object(restore, "_append_transition", interrupt_before_commit)
else:
    interruption = patch.object(restore, "_recovery_transaction", interrupt_after_commit)
with interruption:
    if action == "publish":
        with AXNodeStore(source) as store:
            request = restore.IsolatedRestoreRequest(root, operation_id, int(rev), checkpoint, True)
            review_isolated_restore_commit_or_hold(store, archive, staged, publication=request)
    else:
        restore.rollback_isolated_restore(
            root, operation_id=operation_id, expected_revision=int(rev),
            allow_isolated_write=True,
        )
raise AssertionError("did not reach interruption point")
"""


class IsolatedRestoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = AXNodeStore(self.root / "source")
        self.addCleanup(self.store.close)
        self.memory = AXNodeMemory(self.store)
        self.addCleanup(self.memory.close)
        self.evidence = EvidenceLedger(self.store, create=True)
        self.addCleanup(self.evidence.close)
        self.anchor = self.add_node("first")
        self.archive, self.staged, self.request = self.stage("first", revision=0)

    def add_node(self, name, parents=()):
        digest = self.store.import_node(json.dumps({
            "schema": "eai.axnode.v1", "id": "data." + name, "version": 1,
            "kind": "strategy", "status": "CANDIDATE",
            "signature": {"inputs": {"left": "csv_ref"},
                          "output": "difference_receipt"},
            "pre": [], "post": [], "steps": [{"skill": "csv.reconcile.v1"}],
            "capabilities": ["local.read"], "parent_hashes": list(parents),
            "tests": {"unit": [], "heldout": [], "negative": []}, "evidence": [],
            "provenance": {"author": "eai_synthetic", "source": "local_only"},
            "budget": {"max_steps": 2, "max_seconds": 20},
        }))
        self.memory.remember(tier="EPISODIC", anchor_sha=digest,
                             label="data." + name, captured_at=10)
        self.evidence.append(claim_id="data." + name, source_sha256=digest,
                             polarity="SUPPORT", observed_at=10, expires_at=100, now=20)
        return digest

    def stage(self, name, *, revision):
        if revision == 0:
            self.ledger = create_isolated_restore_ledger(
                self.store, self.root, allow_isolated_write=True,
            )
        archive = create_sidecar_bundle(self.store, self.root / (name + ".zip"))
        staged = restore_sidecar_bundle(archive, self.root / (name + "-staged"))
        preview = review_isolated_restore_commit_or_hold(self.store, archive, staged)
        boundary = inspect_isolated_epoch_boundary(self.store, archive, staged)
        self.assertIsNone(preview.publication)
        self.assertEqual(boundary.status, "SHARED_READ_CHECKPOINT_MATCH")
        self.assertEqual(preview.shared_read_checkpoint_sha256,
                         boundary.shared_read_checkpoint_sha256)
        self.assertIsInstance(preview.shared_read_checkpoint_sha256, str)
        assert preview.shared_read_checkpoint_sha256 is not None
        request = IsolatedRestoreRequest(
            self.ledger, "publish-" + name, revision, preview.shared_read_checkpoint_sha256,
            allow_isolated_write=True,
        )
        return archive, staged, request

    def publish(self, archive=None, staged=None, request=None):
        return review_isolated_restore_commit_or_hold(
            self.store, archive or self.archive, staged or self.staged,
            publication=request or self.request,
        )

    def rollback(self, operation_id, revision):
        return rollback_isolated_restore(
            self.ledger, operation_id=operation_id, expected_revision=revision,
            allow_isolated_write=True,
        )

    def interrupt(self, when, action, archive, staged, request):
        process = subprocess.run(
            [sys.executable, "-c", _CRASH_WORKER, when, action, str(self.store.root),
             str(archive), str(staged), str(self.ledger), request.operation_id,
             str(request.expected_revision), request.reviewed_checkpoint_sha256],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, timeout=20, check=False,
        )
        self.assertEqual(process.returncode, _INTERRUPTED, process.stderr)

    def assert_epoch(self, state, expected_nodes):
        self.assertIsNotNone(state.payload)
        assets = set(dict(state.payload.files)) - {"catalog.sqlite", "memory.sqlite", "evidence.sqlite"}
        self.assertEqual(assets, {"nodes/" + digest + ".axnode" for digest in expected_nodes})
        for db_name, query in (
            ("catalog.sqlite", "SELECT sha256 FROM nodes"),
            ("memory.sqlite", "SELECT anchor_sha FROM entries"),
            ("evidence.sqlite", "SELECT source_sha256 FROM observations"),
        ):
            with state.payload.open_database(db_name) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                self.assertEqual({row[0] for row in db.execute(query)}, set(expected_nodes))
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute("CREATE TABLE denied (value INTEGER)")
                with self.assertRaises(sqlite3.DatabaseError):
                    db.execute("ATTACH DATABASE ? AS denied", (str(self.store.db_path),))

    def test_publication_contains_the_full_restore_after_inputs_are_removed(self):
        protected = (self.store.db_path, self.memory.store.root / "axnode_memory.sqlite",
                     self.evidence.path, self.archive, *self.staged.iterdir(),
                     self.store.nodes_dir / (self.anchor + ".axnode"))
        before = {path: path.read_bytes() for path in protected}
        result = self.publish()
        self.assertFalse(result.can_commit_to_live)
        self.assertFalse(result.originals_touched)
        self.assertEqual(result.status, "ISOLATED_RESTORE_PUBLISHED")
        self.assertEqual({path: path.read_bytes() for path in protected}, before)

        self.archive.unlink()
        for path in self.staged.iterdir():
            path.unlink()
        self.staged.rmdir()
        self.store.close()
        state = recover_isolated_restore(self.ledger)
        self.assertEqual(state.revision, 1)
        self.assertEqual(state.epoch_revision, 1)
        self.assertEqual(state.payload_sha256, result.publication.payload_sha256)
        self.assert_epoch(state, {self.anchor})
        self.assertEqual(self.publish().publication, result.publication)

    def test_rollback_restores_previous_revision_and_rejects_aba_writer(self):
        previous = self.publish().publication
        child = self.add_node("second", parents=(self.anchor,))
        second = self.stage("second", revision=1)
        self.assertEqual(self.publish(*second).publication.epoch_revision, 2)
        current = recover_isolated_restore(self.ledger)
        self.assert_epoch(current, {self.anchor, child})
        self.assertIsNotNone(current.payload)
        assert current.payload is not None
        with current.payload.open_database("catalog.sqlite") as db:
            self.assertEqual(db.execute("SELECT child_sha, parent_sha FROM parents").fetchall(),
                             [(child, self.anchor)])

        rolled = self.rollback("undo-second", 2)
        self.assertEqual((rolled.revision, rolled.epoch_revision), (3, 1))
        state = recover_isolated_restore(self.ledger)
        self.assertEqual(state.payload_sha256, previous.payload_sha256)
        self.assert_epoch(state, {self.anchor})
        with self.assertRaisesRegex(ValueError, "revision changed"):
            self.publish(second[0], second[1], request=replace(second[2], operation_id="stale"))
        self.assertEqual(self.publish(*second).publication.epoch_revision, 2)
        self.assertEqual(self.rollback("undo-first", 3).epoch_revision, None)
        self.assertEqual(self.rollback("undo-second", 2), rolled)
        self.assertIsNone(recover_isolated_restore(self.ledger).payload)

    def test_precommit_process_interruption_keeps_previous_epoch_and_can_retry(self):
        self.publish()
        child = self.add_node("second", parents=(self.anchor,))
        second = self.stage("second", revision=1)
        self.interrupt("before", "publish", *second)
        self.assertTrue((self.ledger / "epoch.sqlite-journal").exists())
        recovered = recover_isolated_restore(self.ledger)
        self.assertEqual(recovered.revision, 1)
        self.assert_epoch(recovered, {self.anchor})
        self.assertEqual(self.publish(*second).publication.revision, 2)
        self.assert_epoch(recover_isolated_restore(self.ledger), {self.anchor, child})

    def test_committed_publication_survives_lost_reply_without_reopening_source(self):
        self.interrupt("after", "publish", self.archive, self.staged, self.request)
        recovered = recover_isolated_restore(self.ledger)
        self.assertEqual(recovered.revision, 1)
        self.assert_epoch(recovered, {self.anchor})
        self.store.close()
        self.assertEqual(self.publish().publication.payload_sha256, recovered.payload_sha256)
        self.assertEqual(recover_isolated_restore(self.ledger).revision, 1)

    def test_rollback_interruption_and_lost_reply(self):
        self.publish()
        undo = replace(self.request, operation_id="undo", expected_revision=1)
        self.interrupt("before", "rollback", self.archive, self.staged, undo)
        self.assertEqual(recover_isolated_restore(self.ledger).epoch_revision, 1)
        self.interrupt("after", "rollback", self.archive, self.staged, undo)
        state = recover_isolated_restore(self.ledger)
        self.assertIsNone(state.epoch_revision)
        self.assertEqual(state.revision, 2)
        self.assertEqual(self.rollback("undo", 1).revision, 2)

    def test_parallel_writers_serialize_with_a_single_revision_winner(self):
        barrier = Barrier(2, timeout=10)

        def writer(operation_id):
            with AXNodeStore(self.store.root) as store:
                barrier.wait()
                try:
                    result = review_isolated_restore_commit_or_hold(
                        store, self.archive, self.staged,
                        publication=replace(self.request, operation_id=operation_id),
                    )
                except ValueError as exc:
                    return str(exc)
                return result.status

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(writer, ["race-a", "race-b"]))
        self.assertCountEqual(results, ["ISOLATED_RESTORE_PUBLISHED",
                                       "isolated recovery revision changed"])
        self.assertEqual(recover_isolated_restore(self.ledger).revision, 1)

    def test_changed_checkpoint_or_reused_operation_id_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "differs from the reviewed checkpoint"):
            self.publish(request=replace(self.request, reviewed_checkpoint_sha256="0" * 64))
        self.assertEqual(recover_isolated_restore(self.ledger).revision, 0)
        self.publish()
        with self.assertRaisesRegex(ValueError, "binds a different request"):
            self.publish(request=replace(self.request, reviewed_checkpoint_sha256="0" * 64))
        self.assertEqual(recover_isolated_restore(self.ledger).revision, 1)

    def test_concurrent_source_commit_invalidates_captured_payload(self):
        capture = sidecar_coherence_review._capture_epoch_payload

        def commit_during_capture(*args):
            payload = capture(*args)
            with EvidenceLedger(self.store, append_existing=True) as writer:
                writer.append(claim_id="data.drift", source_sha256=self.anchor,
                              polarity="SUPPORT", observed_at=10, expires_at=100, now=20)
            return payload

        with patch.object(sidecar_coherence_review, "_capture_epoch_payload", commit_during_capture):
            with self.assertRaisesRegex(ValueError, "HOLD_SOURCE_CHECKPOINT_UNAVAILABLE"):
                self.publish()
        self.assertEqual(recover_isolated_restore(self.ledger).revision, 0)

    def test_changed_staged_copy_and_active_index_cannot_be_published(self):
        marker = next(self.staged.glob("*.sha256"))
        original_marker = marker.read_bytes()
        marker.write_bytes(b"0" * 64 + b"\n")
        with self.assertRaisesRegex(ValueError, "completion marker mismatched"):
            self.publish()
        marker.write_bytes(original_marker)
        with self.store.db:
            self.store.db.execute("UPDATE nodes SET status='ACTIVE'")
        preview = inspect_isolated_epoch_boundary(self.store, self.archive, self.staged)
        with self.assertRaisesRegex(ValueError, "catalog metadata differs"):
            self.publish(request=replace(self.request,
                                         reviewed_checkpoint_sha256=preview.shared_read_checkpoint_sha256))
        self.assertEqual(recover_isolated_restore(self.ledger).revision, 0)

    def test_explicit_isolation_rejects_original_wrong_source_and_linked_target(self):
        with self.assertRaises(PermissionError):
            self.publish(request=replace(self.request, allow_isolated_write=False))
        with self.assertRaises(PermissionError):
            create_isolated_restore_ledger(self.store, self.store.root, allow_isolated_write=True)
        with self.assertRaises(PermissionError):
            self.publish(request=replace(self.request, recovery_root=self.store.root))
        with self.assertRaises(ValueError):
            rollback_isolated_restore(self.store.root, operation_id="no-original",
                                      expected_revision=0, allow_isolated_write=True)
        source_names = {path.name for path in self.store.root.iterdir()}
        with AXNodeStore(self.root / "different") as different:
            with self.assertRaisesRegex(PermissionError, "different source"):
                review_isolated_restore_commit_or_hold(
                    different, self.archive, self.staged, publication=self.request,
                )
        duplicate = self.root / "linked.sqlite"
        os.link(self.ledger / "epoch.sqlite", duplicate)
        try:
            with self.assertRaisesRegex(ValueError, "linked isolated recovery file"):
                self.publish()
        finally:
            duplicate.unlink()
        self.assertEqual({path.name for path in self.store.root.iterdir()}, source_names)
        self.assertEqual(recover_isolated_restore(self.ledger).revision, 0)

    def test_ledger_relocated_inside_source_cannot_be_reopened_or_rolled_back(self):
        self.publish()
        moved = self.ledger.rename(self.store.root / self.ledger.name)
        with self.assertRaises(PermissionError):
            recover_isolated_restore(moved)
        with self.assertRaises(PermissionError):
            rollback_isolated_restore(moved, operation_id="undo", expected_revision=1,
                                      allow_isolated_write=True)

    def test_accepted_publication_reserves_a_revision_for_rollback(self):
        with patch.object(axnode_restore, "_MAX_REVISIONS", 2):
            self.publish()
            with self.assertRaisesRegex(ValueError, "reserve rollback"):
                self.publish(request=replace(self.request, expected_revision=1,
                                             operation_id="unavailable"))
            self.assertEqual(self.rollback("undo", 1).revision, 2)
            self.assertIsNone(recover_isolated_restore(self.ledger).payload)

    def test_payload_corruption_cannot_be_recovered_or_selected_by_rollback(self):
        self.publish()
        self.add_node("second", parents=(self.anchor,))
        self.publish(*self.stage("second", revision=1))
        with closing(sqlite3.connect(self.ledger / "epoch.sqlite")) as db, db:
            db.execute("DELETE FROM epoch_files WHERE revision = 1 AND name = 'memory.sqlite'")
        self.assertEqual(recover_isolated_restore(self.ledger).epoch_revision, 2)
        with self.assertRaisesRegex(ValueError, "isolated epoch"):
            self.rollback("undo", 2)
        with closing(sqlite3.connect(self.ledger / "epoch.sqlite")) as db, db:
            db.execute("DELETE FROM epoch_files WHERE revision = 2 AND name = 'memory.sqlite'")
        with self.assertRaisesRegex(ValueError, "isolated epoch"):
            recover_isolated_restore(self.ledger)


if __name__ == "__main__":
    unittest.main()
