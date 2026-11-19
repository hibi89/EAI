"""C20/C21 local CLI does not print private inputs or execute real tools."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

from eai.__main__ import main
from eai.contracts import ProblemSpec
from eai.player_cli import player_preview


class PlayerCLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.problem_file = self.root / "problem.json"
        self.plan_file = self.root / "plan.json"
        self.problem: dict[str, Any] = {
            "version": 1, "id": "synthetic.cli", "goal": "PRIVATE user question",
            "domain": "research", "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["safety"],
            "oracle": "synthetic.only", "permissions": ["pure"],
            "budget": {"max_steps": 4, "max_seconds": 30},
            "risk": "LOW",
        }
        digest = ProblemSpec.validate(self.problem).digest()
        self.plan: dict[str, Any] = {
            "version": 1, "problem_sha256": digest,
            "steps": [
                {"id": "step01", "operator": "synthetic.noop.v1",
                 "requires": [], "capability": "pure"},
                {"id": "step02", "operator": "synthetic.noop.v1",
                 "requires": ["step01"], "capability": "pure"},
            ], "budget": {"max_steps": 3, "max_seconds": 20},
        }
        self.write()

    def write(self):
        self.problem_file.write_text(json.dumps(self.problem), encoding="utf-8")
        self.plan_file.write_text(json.dumps(self.plan), encoding="utf-8")

    def test_pure_player_cli_executes_only_noop_and_prints_no_private_goal(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            report = player_preview(self.problem_file, self.plan_file)
        self.assertEqual(report["status"], "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED")
        self.assertEqual(report["external_actions"], 0)
        self.assertEqual(report["original_writes"], 0)
        self.assertEqual(report["interpreted_step_count"], 2)
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertFalse(report["active_promotion"])

    def test_actual_cli_command_returns_synthetic_receipt(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["player-preview",
                         "--problem-file", str(self.problem_file),
                         "--plan-file", str(self.plan_file)])
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED")

    def test_cli_unsupported_operator_is_denied_without_executing(self):
        self.plan["steps"][0]["operator"] = "csv.reconcile.v1"
        self.plan["steps"][0]["capability"] = "local.read"
        self.problem["permissions"] = ["pure", "local.read"]
        self.plan["problem_sha256"] = ProblemSpec.validate(self.problem).digest()
        self.write()
        report = player_preview(self.problem_file, self.plan_file)
        self.assertEqual(report["execution"], "DENIED")
        self.assertEqual(report["status"], "HOLD_POLICY_DENIED")

    def test_invalid_json_does_not_echo_secret_or_path(self):
        self.plan_file.write_text('{"secret": "PRIVATE", invalid',
                                  encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["player-preview",
                         "--problem-file", str(self.problem_file),
                         "--plan-file", str(self.plan_file)])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn("PRIVATE", err.getvalue())
        self.assertNotIn(str(self.plan_file), err.getvalue())

    def test_cancelled_preview_never_claims_all_steps_ran(self):
        report = player_preview(
            self.problem_file, self.plan_file, cancel_before_step="step02")
        self.assertEqual(report["status"], "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED")
        self.assertEqual(report["interpreted_step_count"], 1)
