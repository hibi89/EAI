"""C05 explicit multi-DB epoch uncertainty after integrity-only restore."""
import json
from pathlib import Path
import tempfile
import unittest

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

    def test_corrupt_source_node_blocks_coherence_claim(self):
        digest = self.store.hashes()[0]
        (self.store.root / "nodes" / (digest + ".axnode")).write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "source AXNODE integrity"):
            review_isolated_cross_db_coherence(
                self.store, self.archive, self.isolated)


if __name__ == "__main__":
    unittest.main()
