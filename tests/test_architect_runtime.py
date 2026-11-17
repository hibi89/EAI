"""Local architect-preview wiring tests with disposable synthetic AXNODE files."""
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.axnode_store import AXNodeStore
from eai.architect_runtime import preview_architecture
from eai.__main__ import main


class ArchitectRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "axnode"
        with AXNodeStore(self.root) as store:
            for name in ("data.first", "data.second"):
                store.import_node(json.dumps(self.node(name)))
        self.problem_path = self.base / "problem.json"
        self.problem_path.write_text(json.dumps(self.problem()), encoding="utf-8")

    @staticmethod
    def node(name):
        return {
            "schema": "eai.axnode.v1", "id": name, "version": 1,
            "kind": "strategy", "status": "CANDIDATE",
            "signature": {"inputs": {"csv": "csv_ref"},
                          "output": "difference_receipt"},
            "pre": ["read_only"], "post": ["must_verify"],
            "steps": [{"skill": "csv.reconcile.v1"}],
            "capabilities": ["local.read"], "parent_hashes": [],
            "tests": {"unit": [], "heldout": [], "negative": []}, "evidence": [],
            "provenance": {"author": "EAI_DESIGN", "source": "synthetic_only"},
            "budget": {"max_steps": 1, "max_seconds": 15},
        }

    @staticmethod
    def problem():
        return {
            "version": 1, "id": "synthetic.preview",
            "goal": "PRIVATE user question should never be copied",
            "domain": "data", "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["accuracy"],
            "oracle": "synthetic.oracle", "permissions": ["local.read"],
            "budget": {"max_steps": 3, "max_seconds": 60}, "risk": "LOW",
        }

    def test_architect_explanation_cli_sanitizes_private_goal(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["explain-preview", "--kind", "architect",
                         "--problem-file", str(self.problem_path),
                         "--axnode-root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        explanation = json.loads(out.getvalue())
        self.assertEqual(explanation["kind"], "ARCHITECT")
        self.assertEqual(explanation["status"], "CANDIDATES_UNVERIFIED")
        self.assertEqual(len(explanation["alternatives"]), 2)
        self.assertFalse(explanation["verified_real_world"])
        self.assertNotIn("PRIVATE", out.getvalue())

    def test_architect_explanation_text_is_no_network(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["explain-preview", "--kind", "architect",
                             "--problem-file", str(self.problem_path),
                             "--axnode-root", str(self.root),
                             "--format", "text"])
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        self.assertIn("EAI ARCHITECT - UNVERIFIED ADVISORY", out.getvalue())
        self.assertNotIn("PRIVATE", out.getvalue())

    def test_local_preview_returns_two_unverified_plans_without_prompt(self):
        report = preview_architecture(self.problem_path, self.root)
        self.assertEqual(report["status"], "CANDIDATES_UNVERIFIED")
        self.assertEqual(len(report["advisory_plans"]), 2)
        self.assertEqual(report["execution"], "NOT_EXECUTED")
        self.assertEqual(report["truth_status"], "UNVERIFIED")
        self.assertNotIn("PRIVATE user question", json.dumps(report))
        for entry in report["advisory_plans"]:
            self.assertEqual(entry["status"], "ADVISORY_UNVERIFIED_NOT_EXECUTED")

    def test_cli_subcommand_exposes_read_only_architect_preview(self):
        output = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(output), redirect_stderr(err):
            status = main(["architect-preview", "--problem-file", str(self.problem_path),
                           "--axnode-root", str(self.root)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "CANDIDATES_UNVERIFIED")
        self.assertEqual(err.getvalue(), "")

    def test_missing_existing_library_denied_without_creating_it(self):
        missing = self.base / "nonexistent-library"
        with self.assertRaises(ValueError):
            preview_architecture(self.problem_path, missing)
        self.assertFalse(missing.exists())

    def test_unknown_field_is_denied_and_cli_never_leaks_private_goal(self):
        raw = self.problem()
        raw["dangerous"] = "PRIVATE password"
        self.problem_path.write_text(json.dumps(raw), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["architect-preview", "--problem-file", str(self.problem_path),
                         "--axnode-root", str(self.root)])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("ARCHITECT_PREVIEW_INVALID_OR_UNAVAILABLE", err.getvalue())
        self.assertNotIn("PRIVATE", err.getvalue())

    def test_missing_approval_and_no_network_during_preview(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            result = preview_architecture(self.problem_path, self.root)
        self.assertEqual(result["model"], "LOCAL_CPU_ONLY")
        self.assertNotIn("VERIFIED", [p["status"] for p in result["advisory_plans"]])
        self.assertEqual(result["execution"], "NOT_EXECUTED")

    def test_explicit_contradiction_cannot_yield_advisory_plan(self):
        raw = self.problem()
        raw["hard_constraints"] = ["must:data.first", "forbid:data.first"]
        self.problem_path.write_text(json.dumps(raw), encoding="utf-8")
        report = preview_architecture(self.problem_path, self.root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["advisory_plans"], [])
        self.assertEqual(report["design_blocked_reason"],
                         "CONTRADICTORY_HARD_CONSTRAINTS")


if __name__ == "__main__":
    unittest.main()
