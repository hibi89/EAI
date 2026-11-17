"""Synthetic-only immutable AXNODE store, migration and tamper regression."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from eai.axnode_schema import parse_axnode
from eai.axnode_store import AXNodeStore


class AXNodeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "new-axnode-library"

    @staticmethod
    def example():
        return {
            "schema":"eai.axnode.v1","id":"data.csv.key_diff","version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"left":"csv_ref","right":"csv_ref"},
                         "output":"difference_receipt"},
            "pre":["authorized_read_only_sources"],"post":["verified_receipt"],
            "steps":[{"skill":"csv.reconcile.v1"},
                     {"skill":"evidence.verify_receipt.v1"}],
            "capabilities":["local.read"],"parent_hashes":[],
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"local_verified_only"},
            "budget":{"max_steps":5,"max_seconds":60}
        }

    def test_import_restart_idempotence_and_immutable_version(self):
        raw = self.example()
        with AXNodeStore(self.root) as db:
            h = db.import_node(json.dumps(raw))
            self.assertEqual(h, db.import_node(json.dumps(raw)))
            self.assertEqual(db.get(h).as_dict(), raw)
            self.assertEqual(db.audit()["invalid_hashes"], [])
        with AXNodeStore(self.root) as db:
            self.assertEqual(db.hashes(), [h])
            altered = copy.deepcopy(raw)
            altered["pre"].append("different")
            with self.assertRaisesRegex(ValueError, "version conflict"):
                db.import_node(json.dumps(altered))
            self.assertEqual(db.hashes(), [h])

    def test_graph_missing_parent_and_parent_child(self):
        raw = self.example()
        with AXNodeStore(self.root) as db:
            bogus = copy.deepcopy(raw)
            bogus["id"] = "another.strategy"
            bogus["parent_hashes"] = ["f"*64]
            with self.assertRaisesRegex(ValueError, "parent"):
                db.import_node(json.dumps(bogus))
            h1 = db.import_node(json.dumps(raw))
            child = copy.deepcopy(raw)
            child["id"]="data.csv.more"
            child["parent_hashes"]=[h1]
            h2 = db.import_node(json.dumps(child))
            self.assertEqual(db.parents_of(h2),(h1,))
            self.assertEqual(db.children_of(h1),(h2,))
            self.assertEqual(db.audit()["sqlite_integrity"],"ok")

    def test_tampered_content_fails_and_never_overwritten(self):
        with AXNodeStore(self.root) as db:
            raw = json.dumps(self.example())
            h = db.import_node(raw)
            file = self.root / "nodes" / (h+".axnode")
            file.write_text("malicious")
            with self.assertRaises(ValueError):
                db.get(h)
            with self.assertRaises(ValueError):
                db.import_node(raw)
            self.assertEqual(db.audit()["invalid_hashes"],[h])
            self.assertEqual(file.read_text(),"malicious")

    def test_unindexed_orphan_is_detected_without_auto_delete(self):
        with AXNodeStore(self.root) as db:
            node = parse_axnode(json.dumps(self.example()))
            path = self.root / "nodes" / (node.sha256+".axnode")
            path.write_bytes(node.canonical)
            self.assertEqual(db.audit()["orphan_files"],[path.name])
            self.assertEqual(db.import_node(json.dumps(self.example())),node.sha256)
            self.assertEqual(db.audit()["orphan_files"],[])

    def test_unknown_legacy_db_rejected_unchanged(self):
        self.root.mkdir()
        path = self.root / "axnodes.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE legacy(user_data TEXT)")
            db.execute("INSERT INTO legacy VALUES ('keep')")
        with self.assertRaisesRegex(ValueError,"version"):
            AXNodeStore(self.root)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute("SELECT user_data FROM legacy").fetchone()[0],"keep")

    def test_reject_symlinked_root_when_supported(self):
        self.root.parent.mkdir(parents=True,exist_ok=True)
        target = self.root.parent / "real"
        target.mkdir()
        link = self.root.parent / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ValueError):
            AXNodeStore(link)

    def test_invalid_node_fails_before_db_publication(self):
        with AXNodeStore(self.root) as db:
            raw = self.example()
            raw["steps"]=[{"skill":"shell.execute"}]
            with self.assertRaises(ValueError):
                db.import_node(json.dumps(raw))
            self.assertEqual(db.hashes(), [])
            self.assertFalse(list((self.root/"nodes").glob("*.axnode")))


if __name__ == "__main__":
    unittest.main()
