"""Synthetic negative-memory and parent-withdrawal review, never activation."""
import json
from pathlib import Path
import tempfile
import unittest

from eai.axnode_store import AXNodeStore
from eai.axnode_memory import AXNodeMemory
from eai.axnode_memory_review import review_memory_reuse


class MemoryReuseReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"axnode"
        self.store=AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        self.parent=self.store.import_node(json.dumps(self.node("data.parent")))
        self.child=self.store.import_node(json.dumps(self.node("data.child",[self.parent])))
        self.memory=AXNodeMemory(self.store)
        self.addCleanup(self.memory.close)

    @staticmethod
    def node(name,parents=None):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"csv":"csv_ref"},"output":"difference_receipt"},
            "pre":["authorized_read_only"],"post":["verified_later"],
            "steps":[{"skill":"csv.reconcile.v1"}],"capabilities":["local.read"],
            "parent_hashes":parents or [],
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"local_synthetic_only"},
            "budget":{"max_steps":2,"max_seconds":20}
        }

    def test_positive_observation_remains_unverified(self):
        self.memory.remember(tier="PROCEDURAL",anchor_sha=self.parent,
                             label="csv.review",outcome="SUCCESS_OBSERVED",captured_at=20)
        review=review_memory_reuse(self.memory,"csv",now=21)
        self.assertEqual(len(review),1)
        self.assertEqual(review[0].disposition,"UNVERIFIED_CANDIDATE_ONLY")
        self.assertEqual(review[0].authority,"NONE_UNVERIFIED")

    def test_negative_memory_suppresses_conflicting_positive(self):
        self.memory.remember(tier="PROCEDURAL",anchor_sha=self.parent,
                             label="csv.review",captured_at=20)
        self.memory.remember(tier="NEGATIVE",anchor_sha=self.child,
                             label="csv.review",outcome="FAILURE_OBSERVED",
                             captured_at=21)
        review=review_memory_reuse(self.memory,"csv",now=30)
        self.assertEqual(len(review),2)
        self.assertIn("REVIEW_NEGATIVE_OUTCOME",{x.disposition for x in review})
        self.assertIn("REVIEW_CONTRADICTED_BY_NEGATIVE_MEMORY",
                      {x.disposition for x in review})

    def test_withdrawn_parent_invalidates_descendant_recommendation(self):
        self.memory.remember(tier="EPISODIC",anchor_sha=self.child,
                             label="csv.child",captured_at=10)
        review=review_memory_reuse(self.memory,"csv",
                                   withdrawn_hashes=(self.parent,),now=11)
        self.assertEqual(review[0].disposition,"REVIEW_WITHDRAWN_PARENT")

    def test_expired_working_memory_is_not_reused(self):
        self.memory.remember(tier="WORKING",anchor_sha=self.parent,
                             label="csv.short",captured_at=10,ttl_seconds=5)
        self.assertEqual(review_memory_reuse(self.memory,"csv",now=15),())

    def test_invalid_withdrawn_reference_and_no_mutation(self):
        self.memory.remember(tier="SEMANTIC",anchor_sha=self.parent,
                             label="csv.class",captured_at=2)
        before=(self.root/"nodes"/(self.parent+".axnode")).read_bytes()
        with self.assertRaises(KeyError):
            review_memory_reuse(self.memory,"csv",withdrawn_hashes=("f"*64,))
        self.assertEqual(before,(self.root/"nodes"/(self.parent+".axnode")).read_bytes())


if __name__ == "__main__":
    unittest.main()
