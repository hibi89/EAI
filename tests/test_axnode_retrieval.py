"""Local, no-cloud indexed lookup and graph retrieval with integrity checks."""
import copy
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_retrieval import AXNodeRetriever
from eai.axnode_store import AXNodeStore


class AXNodeRetrievalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "axnode"
        self.store = AXNodeStore(self.root)
        self.addCleanup(self.store.close)

    @staticmethod
    def node(name="data.csv.key_diff", output="difference_receipt", parents=None):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"left":"csv_ref","right":"csv_ref"},
                         "output":output},
            "pre":["authorized_read_only_sources"],
            "post":["independently_verified_receipt"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":parents or [],
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"local_verified_only"},
            "budget":{"max_steps":5,"max_seconds":60}
        }

    def test_lexical_lookup_and_type_filter_no_execution(self):
        a = self.store.import_node(json.dumps(self.node()))
        self.store.import_node(json.dumps(self.node("data.csv.audit_again","text")))
        retriever = AXNodeRetriever(self.store)
        result = retriever.find("csv", output_type="difference_receipt")
        self.assertEqual([item.sha256 for item in result], [a])
        self.assertEqual(result[0].provenance, "LOCAL_CANDIDATE_UNVERIFIED")
        self.assertGreater(result[0].score, 0)
        self.assertEqual(retriever.find("nonexistent_keyword"), ())

    def test_graph_related_neighborhood_and_repeatability(self):
        a = self.store.import_node(json.dumps(self.node()))
        b = self.store.import_node(json.dumps(self.node("data.csv.child","text",[a])))
        ret = AXNodeRetriever(self.store)
        self.assertEqual(tuple(x.sha256 for x in ret.find("",related_to=a)),(a,b))
        self.assertEqual(ret.find("csv"),ret.find("csv"))

    def test_index_tracks_new_nodes_after_initialization(self):
        retriever = AXNodeRetriever(self.store)
        self.assertEqual(retriever.find("data"),())
        h = self.store.import_node(json.dumps(self.node()))
        self.assertEqual(retriever.find("data")[0].sha256,h)

    def test_tamper_is_rejected_even_if_index_still_contains_match(self):
        a = self.store.import_node(json.dumps(self.node()))
        ret = AXNodeRetriever(self.store)
        (self.root/"nodes"/(a+".axnode")).write_text("tampered")
        with self.assertRaises(ValueError):
            ret.find("csv")

    def test_invalid_filters_and_match_injection_safe(self):
        self.store.import_node(json.dumps(self.node()))
        retriever = AXNodeRetriever(self.store)
        for invalid in ["\x00", "a"*301]:
            with self.assertRaises(ValueError):
                retriever.find(invalid)
        for invalid_limit in [0, True, 26]:
            with self.assertRaises(ValueError):
                retriever.find("csv",limit=invalid_limit)
        with self.assertRaises(ValueError):
            retriever.find("csv",output_type="shell_code")
        self.assertEqual(retriever.find('csv" OR malicious*'),retriever.find('csv" OR malicious*'))

    def test_no_network_in_retrieval(self):
        self.store.import_node(json.dumps(self.node()))
        with patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.assertEqual(len(AXNodeRetriever(self.store).find("csv")),1)


if __name__ == "__main__":
    unittest.main()
