"""C05 explicit multi-DB epoch uncertainty after integrity-only restore."""
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.axnode_memory import AXNodeMemory
from eai.evidence_ledger import EvidenceLedger
from eai.axnode_sidecar_backup import create_sidecar_bundle, restore_sidecar_bundle
from eai.sidecar_coherence_review import review_isolated_cross_db_coherence


class SidecarCoherenceReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = AXNodeStore(self.root / "source")
        self.addCleanup(self.store.close)
        anchor = self.store.import_node(json.dumps({
            "schema": "eai.axnode.v1", "id": "data.synthetic", "version": 1,
            "kind": "strategy", "status": "CANDIDATE",
            "signature": {"inputs": {"left": "csv_ref"},
                          "output": "difference_receipt"},
            "pre": ["authorized_read_only"], "post": ["verify_later"],
            "steps": [{"skill": "csv.reconcile.v1"}],
            "capabilities": ["local.read"], "parent_hashes": [],
            "tests": {"unit": [], "heldout": [], "negative": []},
            "evidence": [],
            "provenance": {"author": "eai_synthetic", "source": "local_only"},
            "budget": {"max_steps": 2, "max_seconds": 20},
        }))
        with AXNodeMemory(self.store) as memory:
            memory.remember(tier="EPISODIC", anchor_sha=anchor,
                            label="data.synthetic", captured_at=10)
        with EvidenceLedger(self.store, create=True) as evidence:
            evidence.append(claim_id="data.synthetic", source_sha256=anchor,
                            polarity="SUPPORT", observed_at=10,
                            expires_at=100, now=20)
        self.archive = self.root / "backups.zip"
        self.isolated = self.root / "isolated"
        create_sidecar_bundle(self.store, self.archive)
        restore_sidecar_bundle(self.archive, self.isolated)

    def test_valid_restore_does_not_claim_common_epoch_or_live_binding(self):
        before = tuple(self.store.hashes())
        result = review_isolated_cross_db_coherence(
            self.store, self.archive, self.isolated)
        self.assertEqual(result.disposition,
                         "HOLD_CROSS_DB_TRANSACTION_EPOCH_UNPROVEN")
        self.assertEqual(result.sidecar_count, 2)
        self.assertEqual(result.anchor_count, 1)
        self.assertFalse(result.same_transaction_epoch_proven)
        self.assertFalse(result.may_bind_to_live_store)
        self.assertFalse(result.source_data_modified)
        self.assertEqual(before, tuple(self.store.hashes()))

    def test_missing_complete_marker_fails_before_coherence_review(self):
        (self.isolated / ".eai-restore-complete.sha256").unlink()
        with self.assertRaises(ValueError):
            review_isolated_cross_db_coherence(
                self.store, self.archive, self.isolated)

    def test_source_sidecar_drift_is_detected_without_merging(self):
        anchor = self.store.hashes()[0]
        with EvidenceLedger(self.store, append_existing=True) as evidence:
            evidence.append(claim_id="data.second", source_sha256=anchor,
                            polarity="REFUTE", observed_at=15,
                            expires_at=120, now=20)
        result = review_isolated_cross_db_coherence(
            self.store, self.archive, self.isolated)
        self.assertEqual(result.disposition, "HOLD_SOURCE_SIDECAR_DRIFT")
        self.assertTrue(result.source_sidecar_drift_detected)
        self.assertFalse(result.may_bind_to_live_store)

    def test_source_mutation_during_audit_is_distinguished_from_old_snapshot(self):
        import eai.sidecar_coherence_review as module
        original = module.audit_isolated_sidecar_restore
        anchor = self.store.hashes()[0]
        def write_during_read(store, archive, root):
            with EvidenceLedger(self.store, append_existing=True) as evidence:
                evidence.append(claim_id="data.changed", source_sha256=anchor,
                                polarity="REFUTE", observed_at=15,
                                expires_at=120, now=20)
            return original(store, archive, root)
        with patch.object(module, "audit_isolated_sidecar_restore",
                          side_effect=write_during_read):
            result = review_isolated_cross_db_coherence(
                self.store, self.archive, self.isolated)
        self.assertEqual(result.disposition, "HOLD_SOURCE_CHANGED_DURING_AUDIT")
        self.assertTrue(result.source_sidecar_drift_detected)

    def test_source_memory_metadata_tamper_rejected_not_silently_coherent(self):
        path = self.store.root / "axnode_memory.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("UPDATE entries SET tier='NEGATIVE'")
        with self.assertRaisesRegex(ValueError, "indexed metadata mismatch"):
            review_isolated_cross_db_coherence(
                self.store, self.archive, self.isolated)

    def test_source_evidence_metadata_tamper_rejected(self):
        path = self.store.root / "evidence_ledger.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("UPDATE observations SET polarity='REFUTE'")
        with self.assertRaisesRegex(ValueError, "indexed metadata mismatch"):
            review_isolated_cross_db_coherence(
                self.store, self.archive, self.isolated)

    def test_source_sidecar_unknown_schema_version_rejected(self):
        path = self.store.root / "axnode_memory.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA user_version=2")
        with self.assertRaisesRegex(ValueError, "unexpected sidecar user version"):
            review_isolated_cross_db_coherence(
                self.store, self.archive, self.isolated)

    def test_corrupt_source_node_blocks_coherence_claim(self):
        digest = self.store.hashes()[0]
        (self.store.root / "nodes" / (digest + ".axnode")).write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "source AXNODE integrity"):
            review_isolated_cross_db_coherence(
                self.store, self.archive, self.isolated)


if __name__ == "__main__":
    unittest.main()
