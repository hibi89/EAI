"""Synthetic observation replay tests, explicitly no verified reward or execution."""
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.axnode_memory import AXNodeMemory
from eai.evidence_ledger import EvidenceLedger
from eai.episode_replay import replay_memory_evidence


class EpisodeReplayTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"axnode"
        self.store=AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        self.anchor=self.store.import_node(json.dumps(self.node("data.first",[])))
        self.child=self.store.import_node(json.dumps(self.node("data.child",[self.anchor])))
        self.memory=AXNodeMemory(self.store)
        self.addCleanup(self.memory.close)
        self.memory.remember(tier="EPISODIC",anchor_sha=self.anchor,
                             label="data.replay",captured_at=100,
                             outcome="SUCCESS_OBSERVED")

    @staticmethod
    def node(name,parents):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"prior":"difference_receipt"},
                         "output":"difference_receipt"},
            "pre":["read_only"],"post":["independent_check_later"],
            "steps":[{"skill":"csv.reconcile.v1"}],"capabilities":["local.read"],
            "parent_hashes":parents,
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"synthetic_only"},
            "budget":{"max_steps":2,"max_seconds":15},
        }

    def evidence(self,polarity="SUPPORT",expires=200):
        ledger=EvidenceLedger(self.store,create=True)
        self.addCleanup(ledger.close)
        ledger.append(claim_id="data.replay",source_sha256=self.anchor,
                      polarity=polarity,observed_at=101,
                      expires_at=expires,now=150)
        return ledger

    def test_without_ledger_replay_never_verifies_self_reported_success(self):
        rows=replay_memory_evidence(self.memory,None,"data",now=150)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].evidence_state,"NO_EVIDENCE_LEDGER")
        self.assertEqual(rows[0].disposition,"HOLD_NO_INDEPENDENT_EVIDENCE")
        self.assertFalse(rows[0].automated_learning_allowed)
        self.assertFalse(rows[0].automated_execution_allowed)

    def test_positive_evidence_remains_manual_unverified(self):
        ledger=self.evidence()
        rows=replay_memory_evidence(self.memory,ledger,"data",now=150)
        self.assertEqual(rows[0].evidence_state,"SUPPORTED_UNVERIFIED")
        self.assertEqual(rows[0].disposition,"REPLAYED_UNVERIFIED_FOR_MANUAL_REVIEW")
        self.assertEqual(rows[0].independent_verification,"NOT_ESTABLISHED")

    def test_refutation_is_hold(self):
        ledger=self.evidence("REFUTE")
        rows=replay_memory_evidence(self.memory,ledger,"data",now=150)
        self.assertEqual(rows[0].disposition,"HOLD_CONTRADICTED_EVIDENCE")

    def test_stale_support_is_hold(self):
        ledger=self.evidence("SUPPORT",expires=130)
        rows=replay_memory_evidence(self.memory,ledger,"data",now=150)
        self.assertEqual(rows[0].evidence_state,"STALE_UNVERIFIED")
        self.assertEqual(rows[0].disposition,"HOLD_STALE_EVIDENCE")

    def test_negative_memory_overrides_positive_support(self):
        ledger=self.evidence("SUPPORT")
        self.memory.remember(tier="NEGATIVE",anchor_sha=self.child,
                             label="data.replay",outcome="FAILURE_OBSERVED",
                             captured_at=140)
        rows=replay_memory_evidence(self.memory,ledger,"data",now=150)
        self.assertIn("REVIEW_CONTRADICTED_BY_NEGATIVE_MEMORY",
                      {r.disposition for r in rows})
        self.assertIn("REVIEW_NEGATIVE_OUTCOME",{r.disposition for r in rows})
        self.assertTrue(all(not r.automated_learning_allowed for r in rows))

    def test_withdrawn_parent_prevents_reuse(self):
        ledger=self.evidence("SUPPORT")
        self.memory.remember(tier="SEMANTIC",anchor_sha=self.child,
                             label="data.other",captured_at=130)
        rows=replay_memory_evidence(self.memory,ledger,"data",
                                    withdrawn_hashes=(self.anchor,),now=150)
        self.assertTrue(all(r.disposition=="REVIEW_WITHDRAWN_PARENT" for r in rows))

    def test_no_network_no_memory_mutation_or_cross_store_blending(self):
        ledger=self.evidence("SUPPORT")
        before=self.memory.db.execute("SELECT count(*) FROM entries").fetchone()[0]
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            replay_memory_evidence(self.memory,ledger,"data",now=150)
        after=self.memory.db.execute("SELECT count(*) FROM entries").fetchone()[0]
        self.assertEqual(before,after)
        with AXNodeStore(self.root/"separate") as other:
            with EvidenceLedger(other,create=True) as other_ledger:
                with self.assertRaisesRegex(ValueError,"cross-store"):
                    replay_memory_evidence(self.memory,other_ledger,"data",now=150)


if __name__=="__main__":
    unittest.main()
