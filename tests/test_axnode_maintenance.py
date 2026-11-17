"""Synthetic-only backup, restore and dependency impact; no user DB touched."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from eai.axnode_store import AXNodeStore
from eai.axnode_maintenance import (
    create_offline_backup, restore_offline_backup, plan_parent_invalidation,
)


class AXNodeMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store_path = self.root / "source"

    @staticmethod
    def node(identifier="data.csv.key_diff", parents=None):
        return {
            "schema":"eai.axnode.v1", "id":identifier, "version":1,
            "kind":"strategy", "status":"CANDIDATE",
            "signature":{"inputs":{"left":"csv_ref", "right":"csv_ref"},
                         "output":"difference_receipt"},
            "pre":["authorized_read_only_sources"],
            "post":["verified_receipt"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"], "parent_hashes":parents or [],
            "tests":{"unit":[], "heldout":[], "negative":[]},
            "evidence":[],
            "provenance":{"author":"EAI_DESIGN", "source":"local_verified_only"},
            "budget":{"max_steps":5, "max_seconds":60},
        }

    def test_snapshot_and_restore_preserve_graph_and_source(self):
        archive, restored = self.root / "snapshot.zip", self.root / "recovered"
        with AXNodeStore(self.store_path) as source:
            a = source.import_node(json.dumps(self.node()))
            b = source.import_node(json.dumps(self.node("data.csv.child", [a])))
            self.assertEqual(plan_parent_invalidation(source, a).affected_sha256, (b,))
            create_offline_backup(source, archive)
            before = source.audit()
        restore_offline_backup(archive, restored)
        with AXNodeStore(restored) as replica:
            self.assertEqual(set(replica.hashes()), {a, b})
            self.assertEqual(replica.parents_of(b), (a,))
            self.assertEqual(replica.audit()["sqlite_integrity"], "ok")
        with AXNodeStore(self.store_path) as source:
            self.assertEqual(source.audit(), before)

    def test_no_backup_or_restore_overwrite(self):
        archive = self.root / "backup.zip"
        with AXNodeStore(self.store_path) as source:
            source.import_node(json.dumps(self.node()))
            create_offline_backup(source, archive)
            original = archive.read_bytes()
            with self.assertRaises(FileExistsError):
                create_offline_backup(source, archive)
            self.assertEqual(archive.read_bytes(), original)
        destination = self.root / "preexisting"
        destination.mkdir()
        marker = destination / "keep.txt"
        marker.write_text("customer original")
        with self.assertRaises(FileExistsError):
            restore_offline_backup(archive, destination)
        self.assertEqual(marker.read_text(), "customer original")

    def test_corrupt_manifest_rejected_without_creating_destination(self):
        archive = self.root / "backup.zip"
        with AXNodeStore(self.store_path) as source:
            source.import_node(json.dumps(self.node()))
            create_offline_backup(source, archive)
        tampered = self.root / "tampered.zip"
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(tampered, "w") as dest:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "catalog.sqlite":
                    data += b"forged"
                dest.writestr(item.filename, data, compress_type=zipfile.ZIP_STORED)
        restored = self.root / "restore-must-not-exist"
        with self.assertRaisesRegex(ValueError, "modified AXNODE SQLite"):
            restore_offline_backup(tampered, restored)
        self.assertFalse(restored.exists())

    def test_lineage_includes_grandchildren_and_fails_on_missing_content(self):
        with AXNodeStore(self.store_path) as source:
            a = source.import_node(json.dumps(self.node()))
            b = source.import_node(json.dumps(self.node("data.csv.child", [a])))
            c = source.import_node(json.dumps(self.node("data.csv.grandchild", [b])))
            impact = plan_parent_invalidation(source, a)
            self.assertEqual(set(impact.affected_sha256), {b, c})
            self.assertEqual(impact.disposition, "REVIEW_REQUIRED_NOT_EXECUTED")
            (self.store_path / "nodes" / (c + ".axnode")).write_bytes(b"broken")
            with self.assertRaises(ValueError):
                plan_parent_invalidation(source, a)

    def test_backup_rejects_orphan_and_keeps_original(self):
        with AXNodeStore(self.store_path) as source:
            source.import_node(json.dumps(self.node()))
            orphan = self.store_path / "nodes" / ("f" * 64 + ".axnode")
            orphan.write_text("do not discard")
            with self.assertRaisesRegex(ValueError, "unreviewed integrity"):
                create_offline_backup(source, self.root / "should-not-exist.zip")
            self.assertEqual(orphan.read_text(), "do not discard")
            self.assertFalse((self.root / "should-not-exist.zip").exists())


if __name__ == "__main__":
    unittest.main()
