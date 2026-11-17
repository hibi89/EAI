"""Synthetic only: five AXNODE metadata tiers without raw prompts or promotion."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from eai.axnode_memory import AXNodeMemory
from eai.axnode_store import AXNodeStore


class AXNodeMemoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "isolated"
        self.store = AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        raw = {
            "schema":"eai.axnode.v1", "id":"data.csv.key_diff", "version":1,
            "kind":"strategy", "status":"CANDIDATE",
            "signature":{"inputs":{"left":"csv_ref"}, "output":"difference_receipt"},
            "pre":["allowed_sources"], "post":["checked_result"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"], "parent_hashes":[],
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"synthetic_only"},
            "budget":{"max_steps":3,"max_seconds":40},
        }
        self.anchor = self.store.import_node(json.dumps(raw))

    def test_tiers_restart_and_provenance_not_verified(self):
        tiers = ("EPISODIC", "SEMANTIC", "PROCEDURAL", "NEGATIVE")
        with AXNodeMemory(self.store) as memory:
            digests = [memory.remember(tier=tier, anchor_sha=self.anchor,
                       label="csv.validation", tags=("csv", "receipt"),
                       outcome="FAILURE_OBSERVED" if tier == "NEGATIVE" else "UNKNOWN",
                       captured_at=150) for tier in tiers]
            self.assertEqual(len(set(digests)), 4)
        with AXNodeMemory(self.store) as reopened:
            results = reopened.find("csv", now=151)
            self.assertEqual(len(results), 4)
            self.assertTrue(all(r["provenance"] == "LOCAL_OBSERVATION_UNVERIFIED"
                                for r in results))
            self.assertEqual(reopened.get(digests[-1])["tier"], "NEGATIVE")

    def test_working_memory_expires_from_lookup_without_deleting_provenance(self):
        with AXNodeMemory(self.store) as memory:
            digest = memory.remember(tier="WORKING", anchor_sha=self.anchor,
                                     label="csv.preview", captured_at=10,
                                     ttl_seconds=30)
            self.assertEqual(len(memory.find("csv", now=39)), 1)
            self.assertEqual(memory.find("csv", now=40), ())
            self.assertEqual(memory.get(digest)["tier"], "WORKING")

    def test_unapproved_text_and_forged_verification_denied(self):
        with AXNodeMemory(self.store) as memory:
            for label in ("raw user prompt", "https://host", "../path", "비밀"):
                with self.subTest(label=label), self.assertRaises(ValueError):
                    memory.remember(tier="PROCEDURAL", anchor_sha=self.anchor, label=label)
            with self.assertRaises(ValueError):
                memory.remember(tier="NEGATIVE", anchor_sha=self.anchor,
                                label="test.failure", outcome="SUCCESS_OBSERVED")
            with self.assertRaises(ValueError):
                memory.remember(tier="EPISODIC", anchor_sha="f"*64,
                                label="synthetic.failure")
            with self.assertRaises(ValueError):
                memory.remember(tier="PROCEDURAL", anchor_sha=self.anchor,
                                label="synthetic", tags=("private user text",))
            self.assertEqual(memory.find(""), ())

    def test_sqlite_metadata_tamper_rejected(self):
        with AXNodeMemory(self.store) as memory:
            digest = memory.remember(tier="EPISODIC", anchor_sha=self.anchor,
                                     label="csv.failure", captured_at=2)
            memory.db.execute("UPDATE entries SET label='forged' WHERE sha256=?", (digest,))
            memory.db.commit()
            with self.assertRaisesRegex(ValueError, "index differs"):
                memory.get(digest)

    def test_memory_never_modifies_existing_axnode_file(self):
        before = (self.root / "nodes" / (self.anchor + ".axnode")).read_bytes()
        with AXNodeMemory(self.store) as memory:
            memory.remember(tier="NEGATIVE", anchor_sha=self.anchor,
                            label="csv.bad_receipt", outcome="FAILURE_OBSERVED")
            self.assertEqual(len(memory.find("csv", tier="NEGATIVE")), 1)
            with self.assertRaises(ValueError):
                memory.find("csv", tier="ACTIVE")
        self.assertEqual((self.root / "nodes" / (self.anchor + ".axnode")).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
