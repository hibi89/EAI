"""Synthetic read-only recovery plan tests. No original DB restore is run."""
import json
from pathlib import Path
import tempfile
import unittest

from eai.axnode_store import AXNodeStore
from eai.axnode_recovery import inspect_recovery_preflight


class RecoveryPreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)/"axnode"
        self.store = AXNodeStore(self.root)
        self.addCleanup(self.store.close)

    def test_clean_catalog_reports_narrow_scope_not_full_restore(self):
        state = inspect_recovery_preflight(self.store)
        self.assertEqual(state.state,"AXNODE_V1_ONLY_CANDIDATE_UNVERIFIED")
        self.assertEqual(state.sidecars, (("memory","NOT_PRESENT"),("evidence","NOT_PRESENT")))
        self.assertEqual(state.disposition,"REVIEW_ONLY_NOT_EXECUTED")

    def test_present_memory_sidecar_prevents_claim_of_complete_backup(self):
        # Valid sidecar is not captured by the old AXNODE v1 ZIP.
        from eai.axnode_memory import AXNodeMemory
        with AXNodeMemory(self.store):
            pass
        before = (self.root/"axnode_memory.sqlite").read_bytes()
        result = inspect_recovery_preflight(self.store)
        self.assertEqual(result.state,"REVIEW_REQUIRED")
        self.assertIn("MEMORY_EXCLUDED_FROM_V1_ARCHIVE",result.source_findings)
        self.assertEqual(before,(self.root/"axnode_memory.sqlite").read_bytes())

    def test_orphan_node_staging_is_review_only(self):
        orphan=self.root/"nodes"/("f"*64+".axnode")
        orphan.write_bytes(b"unreviewed")
        result=inspect_recovery_preflight(self.store)
        self.assertEqual(result.state,"REVIEW_REQUIRED")
        self.assertIn("ORPHAN_OR_STAGING_DATA_REQUIRES_REVIEW",result.source_findings)
        self.assertEqual(orphan.read_bytes(),b"unreviewed")

    def test_symlinked_sidecar_not_opened(self):
        target=self.root/"ordinary.txt"
        target.write_text("private",encoding="utf-8")
        try:
            (self.root/"evidence_ledger.sqlite").symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unsupported")
        state=inspect_recovery_preflight(self.store)
        self.assertIn(("evidence","UNSAFE_SYMLINK"),state.sidecars)
        self.assertEqual(target.read_text(encoding="utf-8"),"private")

    def test_fake_database_requires_manual_review_not_destructive_repair(self):
        sidecar=self.root/"evidence_ledger.sqlite"
        sidecar.write_bytes(b"not sqlite")
        result=inspect_recovery_preflight(self.store)
        self.assertIn(("evidence","SIDECAR_FORMAT_OR_INTEGRITY_REVIEW_REQUIRED"),
                      result.sidecars)
        self.assertEqual(sidecar.read_bytes(),b"not sqlite")


if __name__ == "__main__":
    unittest.main()
