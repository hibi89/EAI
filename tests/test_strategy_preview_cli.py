"""CLI C17/C18 paths never require a network or expose private goal."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from eai.__main__ import main
from eai.axnode_store import AXNodeStore
from eai.research_rank_cli import preview_strategy


class StrategyPreviewCLITests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store_root = self.root / "axnode"
        def node(name, parents):
            return {
                "schema": "eai.axnode.v1", "id": name, "version": 1,
                "kind": "strategy", "status": "CANDIDATE",
                "signature": {"inputs": {"csv": "csv_ref",
                                         "prior": "difference_receipt"},
                              "output": "difference_receipt"},
                "pre": ["synthetic_only"], "post": ["independent_check"],
                "steps": [{"skill": "csv.reconcile.v1"}],
                "capabilities": ["local.read"], "parent_hashes": parents,
                "tests": {"unit": [], "heldout": [], "negative": []},
                "evidence": [],
                "provenance": {"author": "eai_synthetic",
                               "source": "local_only"},
                "budget": {"max_steps": 2, "max_seconds": 20},
            }
        with AXNodeStore(self.store_root) as store:
            a = store.import_node(json.dumps(node("strategy.first", [])))
            b = store.import_node(json.dumps(node("strategy.second", [a])))
        self.refs = a + "," + b
        self.problem = self.root / "problem.json"
        self.problem.write_text(json.dumps({
            "version": 1, "id": "synthetic.preview",
            "goal": "PRIVATE DO NOT PRINT", "domain": "data",
            "state_refs": [], "assumptions": [], "hard_constraints": [],
            "objectives": ["accuracy"], "oracle": "synthetic.fixture",
            "permissions": ["local.read"],
            "budget": {"max_steps": 5, "max_seconds": 90},
            "risk": "LOW",
        }), encoding="utf-8")

    def test_rank_preview_is_synthetic_only(self):
        output = preview_strategy(self.problem, self.store_root, self.refs)
        self.assertEqual(output["status"],
                         "SYNTHETIC_COST_ORDER_ONLY_NOT_LEARNING")
        self.assertFalse(output["automatic_learning"])
        self.assertFalse(output["auto_activation"])
        self.assertNotIn("PRIVATE", str(output))

    def test_cli_outputs_sanitized_result(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["strategy-preview", "--problem-file",
                         str(self.problem), "--axnode-root",
                         str(self.store_root), "--node-hashes", self.refs])
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(json.loads(out.getvalue())["network"],
                         "DISABLED_BY_DESIGN")
        self.assertNotIn("PRIVATE", out.getvalue())

    def test_invalid_seed_denied_and_path_hidden(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["strategy-preview", "--problem-file",
                         str(self.problem), "--axnode-root",
                         str(self.store_root), "--node-hashes",
                         self.refs, "--seed", "-1"])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn(str(self.problem), err.getvalue())
