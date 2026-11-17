"""C22/C23/C24 user CLI paths never enable real effects."""
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eai.__main__ import main
from eai.adapter_stub import AdapterHandshake
from eai.contracts import ProblemSpec, PlanSpec
from eai.policy_gate import plan_digest


class EAIPreviewCLITests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.problem = {
            "version": 1, "id": "synthetic.explain",
            "goal": "PRIVATE never show", "domain": "research",
            "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["safety"],
            "oracle": "synthetic", "permissions": ["pure"],
            "budget": {"max_steps": 2, "max_seconds": 20},
            "risk": "LOW",
        }
        digest = ProblemSpec.validate(self.problem).digest()
        self.plan = PlanSpec.validate({
            "version": 1, "problem_sha256": digest,
            "steps": [{"id": "step01",
                       "operator": "synthetic.noop.v1",
                       "requires": [], "capability": "pure"}],
            "budget": {"max_steps": 1, "max_seconds": 10},
        })
        self.problem_file = self.root / "problem.json"
        self.plan_file = self.root / "plan.json"
        self.handshake_file = self.root / "handshake.json"
        self.problem_file.write_text(json.dumps(self.problem), encoding="utf-8")
        self.plan_file.write_text(json.dumps({
            "version": 1, "problem_sha256": digest,
            "steps": [{"id": "step01", "operator": "synthetic.noop.v1",
                       "requires": [], "capability": "pure"}],
            "budget": {"max_steps": 1, "max_seconds": 10},
        }), encoding="utf-8")
        self.handshake_file.write_text(json.dumps({
            "version": 1, "adapter": "my_local_ai", "nonce": "testnonce1234",
            "problem_sha256": digest, "plan_sha256": plan_digest(self.plan),
            "requested_scope": "CAPABILITY_PREVIEW_ONLY",
            "claimed_consent_sha256": None,
        }), encoding="utf-8")

    def call(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = main(args)
        return result, out.getvalue(), err.getvalue()

    def test_player_explanation_is_sanitized_local_only(self):
        code, out, err = self.call([
            "explain-preview", "--kind", "player",
            "--problem-file", str(self.problem_file),
            "--plan-file", str(self.plan_file)])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertNotIn("PRIVATE", out)
        self.assertEqual(json.loads(out)["status"],
                         "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED")

    def test_disabled_adapter_preview_returns_not_approved(self):
        code, out, err = self.call([
            "adapter-preview", "--problem-file", str(self.problem_file),
            "--plan-file", str(self.plan_file),
            "--handshake-file", str(self.handshake_file)])
        self.assertEqual(code, 2)
        self.assertEqual(err, "")
        decision = json.loads(out)
        self.assertEqual(decision["status"],
                         "STUB_CONTRACT_MATCHED_EXECUTOR_DISABLED")
        self.assertFalse(decision["can_execute"])
        self.assertFalse(decision["grants_consent"])

    def test_resource_preview_mocked_local_rss_without_process(self):
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=128 * 1024 * 1024):
            code, out, err = self.call([
                "resource-preview", "--max-rss-mib", "512",
                "--elapsed-ms", "50", "--steps-completed", "1"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        decision = json.loads(out)
        self.assertFalse(decision["may_start_external_process"])
        self.assertFalse(decision["gpu_required"])

    def test_explain_rejects_mixed_plan_and_root_without_leaking(self):
        code, out, err = self.call([
            "explain-preview", "--kind", "player",
            "--problem-file", str(self.problem_file),
            "--plan-file", str(self.plan_file),
            "--axnode-root", str(self.root)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertNotIn("PRIVATE", err)
        self.assertNotIn(str(self.root), err)

    def test_adapter_invalid_secret_json_is_not_echoed(self):
        self.handshake_file.write_text('{"PRIVATE": "a"}',
                                       encoding="utf-8")
        code, out, err = self.call([
            "adapter-preview", "--problem-file", str(self.problem_file),
            "--plan-file", str(self.plan_file),
            "--handshake-file", str(self.handshake_file)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertNotIn("PRIVATE", err)
