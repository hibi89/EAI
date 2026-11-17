"""Public synthetic B1 CLI exercises the interpreted AXNODE path only."""
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.__main__ import main
from eai.b1_cli import b1_preview


class B1CLITests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base=Path(t.name)
        self.root=self.base/"axnodes"
        with AXNodeStore(self.root) as store:
            a=store.import_node(json.dumps(self.node("data.first",[])))
            b=store.import_node(json.dumps(self.node("data.second",[a])))
        self.nodes=(a,b)
        self.problem=self.base/"problem.json"
        self.problem.write_text(json.dumps({
            "version":1,"id":"synthetic.b1.cli",
            "goal":"PRIVATE source not shown","domain":"data",
            "state_refs":[],"assumptions":[],"hard_constraints":[],
            "objectives":["accuracy"],"oracle":"synthetic.fixture",
            "permissions":["local.read"],
            "budget":{"max_steps":5,"max_seconds":90},"risk":"LOW",
        }),encoding="utf-8")
        self.fixtures=self.base/"synthetic.json"
        self.fixtures.write_text(json.dumps(self.manifest()),encoding="utf-8")

    @staticmethod
    def node(name,parents):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"csv":"csv_ref","prev":"difference_receipt"},
                         "output":"difference_receipt"},
            "pre":["synthetic_only"],"post":["independent_oracle"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":parents,
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"eai_synthetic","source":"local_only"},
            "budget":{"max_steps":2,"max_seconds":20},
        }

    @staticmethod
    def manifest():
        return {
            "version":1,
            "train":[
                {"family":"train.same","left":[["a","1.0"]],
                 "right":[["a","1.00"]],"claimed_different":[]},
                {"family":"train.diff","left":[["b","1"]],
                 "right":[["b","3"]],"claimed_different":["b"]},
            ],
            "heldout":[
                {"family":"heldout.same","left":[["c","4.0"]],
                 "right":[["c","4.00"]],"claimed_different":[]},
                {"family":"heldout.diff","left":[["d","2"],["e","3"]],
                 "right":[["d","2"],["f","3"]],"claimed_different":["e","f"]},
            ],
        }

    def args(self,*, root=None,nodes=None):
        return ["b1-preview","--problem-file",str(self.problem),
                "--axnode-root",str(self.root if root is None else root),
                "--fixture-file",str(self.fixtures),
                "--node-hashes",(",".join(self.nodes) if nodes is None else nodes)]

    def call(self,**kwargs):
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):
            result=main(self.args(**kwargs))
        return result,out.getvalue(),err.getvalue()

    def test_B1_actual_synthetic_interpretation_exposed_without_promotion(self):
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            code,out,err=self.call()
        self.assertEqual(code,0)
        self.assertEqual(err,"")
        report=json.loads(out)
        self.assertEqual(report["comparison"]["status"],
                         "B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED")
        self.assertEqual(report["comparison"]["b1_heldout_compared"],2)
        self.assertFalse(report["real_world_verified"])
        self.assertFalse(report["automatic_learning"])
        self.assertFalse(report["node_activation"])
        self.assertNotIn("PRIVATE",out)

    def test_missing_root_never_autocreates_axnode(self):
        missing=self.base/"absent"
        code,out,err=self.call(root=missing)
        self.assertEqual(code,1)
        self.assertFalse(missing.exists())
        self.assertEqual(out,"")
        self.assertIn("B1_SYNTHETIC_PREVIEW_REJECTED",err)

    def test_untrusted_hash_and_private_field_are_rejected_without_echoing(self):
        code,out,err=self.call(nodes="f"*64+","+"e"*64)
        self.assertEqual(code,1)
        self.assertNotIn("PRIVATE",err)
        self.assertEqual(out,"")
        doc=self.manifest()
        doc["PRIVATE_notes"]="hidden"
        self.fixtures.write_text(json.dumps(doc),encoding="utf-8")
        code,out,err=self.call()
        self.assertEqual(code,1)
        self.assertNotIn("hidden",err)

    def test_poisoned_heldout_must_return_nonzero(self):
        doc=self.manifest()
        doc["heldout"][1]["claimed_different"]=[]
        self.fixtures.write_text(json.dumps(doc),encoding="utf-8")
        code,out,err=self.call()
        self.assertEqual(code,2)
        self.assertEqual(json.loads(out)["comparison"]["status"],
                         "HOLD_B0_UNVERIFIED_OR_LEAK")
        self.assertEqual(err,"")

    def test_original_axnode_content_is_not_mutated(self):
        original={h:(self.root/"nodes"/(h+".axnode")).read_bytes()
                  for h in self.nodes}
        report=b1_preview(self.problem,self.root,self.fixtures,",".join(self.nodes))
        self.assertTrue(report["candidate_synthetic_only"])
        self.assertEqual(original,{h:(self.root/"nodes"/(h+".axnode")).read_bytes()
                                   for h in self.nodes})

    def test_deterministic_result_for_same_fixture_and_candidate(self):
        a=b1_preview(self.problem,self.root,self.fixtures,",".join(self.nodes))
        b=b1_preview(self.problem,self.root,self.fixtures,",".join(self.nodes))
        self.assertEqual(a,b)


if __name__=="__main__":
    unittest.main()
