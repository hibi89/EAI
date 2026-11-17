"""Offline B0 CLI is synthetic-only, exact-source pinned and privacy-minimized."""
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.b0_cli import b0_preview
from eai.__main__ import main


class B0CLITests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base=Path(temp.name)
        self.root=self.base/"axnode"
        with AXNodeStore(self.root) as store:
            a=store.import_node(json.dumps(self.node("data.first",[])))
            b=store.import_node(json.dumps(self.node("data.second",[a])))
        self.nodes=(a,b)
        self.problem=self.base/"problem.json"
        self.problem.write_text(json.dumps({
            "version":1,"id":"synthetic.cli","goal":"PRIVATE user goal",
            "domain":"data","state_refs":[],"assumptions":[],
            "hard_constraints":[],"objectives":["accuracy"],
            "oracle":"synthetic.reference","permissions":["local.read"],
            "budget":{"max_steps":5,"max_seconds":60},"risk":"LOW",
        }),encoding="utf-8")
        self.fixture=self.base/"fixture.json"
        self.fixture.write_text(json.dumps(self.data()),encoding="utf-8")

    @staticmethod
    def node(name,parents):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"csv":"csv_ref","prior":"difference_receipt"},
                         "output":"difference_receipt"},
            "pre":["read_only"],"post":["independent_check"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":parents,
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"eai_synthetic","source":"local_only"},
            "budget":{"max_steps":2,"max_seconds":15},
        }

    @staticmethod
    def data():
        return {
            "version":1,
            "train":[
                {"family":"train.agree","left":[["a","1.0"]],
                 "right":[["a","1.00"]],"claimed_different":[]},
                {"family":"train.diff","left":[["a","2"]],
                 "right":[["a","5"]],"claimed_different":["a"]},
            ],
            "heldout":[
                {"family":"heldout.agree","left":[["b","3.0"]],
                 "right":[["b","3.00"]],"claimed_different":[]},
                {"family":"heldout.missing",
                 "left":[["c","1"],["d","2"]],
                 "right":[["c","1"],["e","3"]],
                 "claimed_different":["d","e"]},
            ],
        }

    def argv(self, *, nodes=None, root=None):
        return ["b0-preview","--problem-file",str(self.problem),
                "--axnode-root",str(self.root if root is None else root),
                "--fixture-file",str(self.fixture),
                "--node-hashes",",".join(self.nodes) if nodes is None else nodes]

    def run_cli(self,**kwargs):
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):
            code=main(self.argv(**kwargs))
        return code,out.getvalue(),err.getvalue()

    def test_local_cli_reports_b0_not_candidate_approval(self):
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            code,out,err=self.run_cli()
        self.assertEqual(code,0)
        report=json.loads(out)
        self.assertEqual(report["baseline"]["status"],
                         "B0_SYNTHETIC_HELDOUT_MATCH_UNVERIFIED")
        self.assertEqual(report["baseline"]["observed_b0_cases"],4)
        self.assertFalse(report["candidate_executed"])
        self.assertFalse(report["new_strategy_verified"])
        self.assertFalse(report["automatic_learning"])
        self.assertFalse(report["node_activation"])
        self.assertEqual(err,"")
        self.assertNotIn("PRIVATE",out)

    def test_missing_library_never_auto_created(self):
        missing=self.base/"missing"
        code,out,err=self.run_cli(root=missing)
        self.assertEqual(code,1)
        self.assertEqual(out,"")
        self.assertFalse(missing.exists())
        self.assertIn("B0_SYNTHETIC_PREVIEW_REJECTED",err)

    def test_unknown_node_hash_is_sanitized_instead_of_traceback(self):
        code,out,err=self.run_cli(nodes="f"*64+","+"e"*64)
        self.assertEqual(code,1)
        self.assertEqual(out,"")
        self.assertNotIn("PRIVATE",err)
        self.assertIn("B0_SYNTHETIC_PREVIEW_REJECTED",err)

    def test_poisoned_heldout_expected_result_returns_nonzero_not_verified(self):
        document=self.data()
        document["heldout"][1]["claimed_different"]=[]
        self.fixture.write_text(json.dumps(document),encoding="utf-8")
        code,out,err=self.run_cli()
        self.assertEqual(code,2)
        self.assertEqual(json.loads(out)["baseline"]["status"],
                         "HOLD_B0_HELDOUT_FAILURE")
        self.assertEqual(err,"")

    def test_unexpected_fixture_field_and_private_payload_not_echoed(self):
        document=self.data()
        document["PRIVATE-password"]="not-for-reply"
        self.fixture.write_text(json.dumps(document),encoding="utf-8")
        code,out,err=self.run_cli()
        self.assertEqual(code,1)
        self.assertEqual(out,"")
        self.assertNotIn("PRIVATE",err)

    def test_invalid_numeric_and_duplicate_data_held_closed(self):
        document=self.data()
        document["train"][0]["left"]=[["a","NaN"]]
        self.fixture.write_text(json.dumps(document),encoding="utf-8")
        code,out,err=self.run_cli()
        self.assertEqual(code,1)
        self.assertEqual(out,"")
        self.assertIn("REJECTED",err)

    def test_original_axnode_content_is_unchanged(self):
        before={(h):(self.root/"nodes"/(h+".axnode")).read_bytes()
                for h in self.nodes}
        preview=b0_preview(self.problem,self.root,self.fixture,
                           ",".join(self.nodes))
        self.assertTrue(preview["synthetic_only"])
        self.assertEqual(before,{(h):(self.root/"nodes"/(h+".axnode")).read_bytes()
                                 for h in self.nodes})


if __name__=="__main__":
    unittest.main()
