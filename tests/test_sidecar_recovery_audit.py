"""Synthetic-only restore audit; no writing into original AXNODE store."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from eai.axnode_store import AXNodeStore
from eai.axnode_memory import AXNodeMemory
from eai.evidence_ledger import EvidenceLedger
from eai.axnode_sidecar_backup import create_sidecar_bundle, restore_sidecar_bundle
from eai.sidecar_recovery_audit import audit_isolated_sidecar_restore


class SidecarRecoveryAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.store = AXNodeStore(self.base / "source")
        self.addCleanup(self.store.close)
        self.anchor = self.store.import_node(json.dumps({
            "schema":"eai.axnode.v1", "id":"data.synthetic", "version":1,
            "kind":"strategy", "status":"CANDIDATE",
            "signature":{"inputs":{"left":"csv_ref"},"output":"difference_receipt"},
            "pre":["authorized_read_only"],"post":["verify_later"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":[],
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"eai_synthetic","source":"local_only"},
            "budget":{"max_steps":2,"max_seconds":20},
        }))

    def make_bundle(self):
        with AXNodeMemory(self.store) as mem:
            mem.remember(tier="EPISODIC",anchor_sha=self.anchor,
                         label="data.fixture",captured_at=10)
        with EvidenceLedger(self.store, create=True) as evidence:
            evidence.append(claim_id="data.fixture",source_sha256=self.anchor,
                            polarity="SUPPORT",observed_at=10,
                            expires_at=100,now=20)
        archive=self.base/"sidecars.zip"
        restored=self.base/"isolated"
        create_sidecar_bundle(self.store,archive)
        restore_sidecar_bundle(archive,restored)
        return archive, restored

    def test_two_sidecars_match_archive_and_still_are_unverified(self):
        archive,root=self.make_bundle()
        before={p.name:p.read_bytes() for p in self.store.root.glob("*.sqlite")}
        audit=audit_isolated_sidecar_restore(self.store,archive,root)
        self.assertEqual(audit.status,
                         "ISOLATED_RESTORE_INTEGRITY_ONLY_UNVERIFIED")
        self.assertEqual(audit.archived_file_count,2)
        self.assertEqual(audit.validated_row_count,2)
        self.assertEqual(audit.matched_anchor_count,1)
        self.assertFalse(audit.bound_into_live_store)
        self.assertFalse(audit.original_data_modified)
        self.assertEqual(before,{p.name:p.read_bytes()
                                 for p in self.store.root.glob("*.sqlite")})

    def test_modified_restored_file_fails_before_any_binding(self):
        archive,root=self.make_bundle()
        path=root/"memory.sqlite"
        path.write_bytes(path.read_bytes()+b"forged")
        with self.assertRaisesRegex(ValueError,"does not match"):
            audit_isolated_sidecar_restore(self.store,archive,root)

    def test_extra_restored_entry_never_trusted(self):
        archive,root=self.make_bundle()
        (root/"unexpected.db").write_bytes(b"private")
        with self.assertRaisesRegex(ValueError,"unexpected restored"):
            audit_isolated_sidecar_restore(self.store,archive,root)
        self.assertEqual((root/"unexpected.db").read_bytes(),b"private")

    def test_missing_restored_db_is_not_silent_success(self):
        archive,root=self.make_bundle()
        (root/"evidence.sqlite").unlink()
        with self.assertRaises(ValueError):
            audit_isolated_sidecar_restore(self.store,archive,root)

    def test_missing_node_content_breaks_reference_binding(self):
        archive,root=self.make_bundle()
        (self.store.root/"nodes"/(self.anchor+".axnode")).write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            audit_isolated_sidecar_restore(self.store,archive,root)

    def test_restoring_directly_into_source_root_is_never_audit_success(self):
        archive,root=self.make_bundle()
        with self.assertRaisesRegex(ValueError,"separate"):
            audit_isolated_sidecar_restore(self.store,archive,self.store.root)

    def test_symlinked_restored_entry_fails_closed(self):
        archive,root=self.make_bundle()
        item=root/"memory.sqlite"
        real=self.base/"memory-copy.sqlite"
        real.write_bytes(item.read_bytes())
        item.unlink()
        try:
            item.symlink_to(real)
        except (OSError,NotImplementedError):
            self.skipTest("symlink unsupported")
        with self.assertRaises(ValueError):
            audit_isolated_sidecar_restore(self.store,archive,root)

    def test_incomplete_isolation_is_not_auto_repaired(self):
        archive,root=self.make_bundle()
        (root/"memory.sqlite").unlink()
        with self.assertRaises(ValueError):
            audit_isolated_sidecar_restore(self.store,archive,root)
        self.assertFalse((root/"memory.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
