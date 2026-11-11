"""P24 goal selector: allowlisted SHA-pinned plans; no automatic execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.goal_selector import select_goal, render_selection


class GoalSelectorP24Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.one = self.root / "one.json"
        self.two = self.root / "two.json"
        self.one.write_text(json.dumps({"version": 1, "kind": "schedule_tasks"}),
                            encoding="utf-8")
        self.two.write_text(json.dumps({"version": 1, "kind": "csv_quality"}),
                            encoding="utf-8")
        self.manifest = self.root / "batch.json"
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(json.dumps({
            "version": 1, "kind": "goal_batch", "continue_on_error": True,
            "items": [
                {"id": "schedule", "goal": "one.json",
                 "sha256": hashlib.sha256(self.one.read_bytes()).hexdigest()},
                {"id": "quality", "goal": "two.json",
                 "sha256": hashlib.sha256(self.two.read_bytes()).hexdigest()}
            ]
        }), encoding="utf-8")

    def test_literal_selects_exact_id_without_running_goal(self):
        result = select_goal(self.manifest, "Please inspect quality")
        self.assertEqual(result["status"], "PROPOSED")
        self.assertEqual(result["selected"]["id"], "quality")
        self.assertEqual(result["method"], "CPU_LITERAL")
        self.assertTrue(result["requires_explicit_execution"])
        self.assertIn("solve-goal", render_selection(result))

    def test_unknown_question_needs_review(self):
        report = select_goal(self.manifest, "Please review that project")
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertIsNone(report["selected"])

    def test_no_partial_id_matching(self):
        report = select_goal(self.manifest, "highquality")
        self.assertIsNone(report["selected"])

    def test_ambiguous_request_needs_review(self):
        report = select_goal(self.manifest, "quality and schedule")
        self.assertIsNone(report["selected"])

    def test_goal_kind_unique_match(self):
        report = select_goal(self.manifest, "Please do csv_quality")
        self.assertEqual(report["selected"]["id"], "quality")

    def test_no_source_values_or_payloads_in_proposal(self):
        report = select_goal(self.manifest, "quality")
        self.assertNotIn('"version": 1, "kind": "csv_quality"',
                         json.dumps(report))
        self.assertEqual(set(report["selected"]),
                         {"id", "goal", "sha256", "kind"})

    def test_source_sha_changed_rejects_without_execution(self):
        self.two.write_text('{"kind":"plan_tasks"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            select_goal(self.manifest, "quality")

    def test_manifest_change_during_model_call_is_detected(self):
        def fake(url, **kwargs):
            self.manifest.write_text('{"replaced":true}', encoding="utf-8")
            return {"message": {"content": '{"version":1,"selected_id":"quality"}'}}
        with patch("eai.goal_selector.fetch_json", side_effect=fake):
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                select_goal(self.manifest, "not literal", use_qwen=True)

    def test_cpu_default_never_contacts_model(self):
        with patch("eai.goal_selector.fetch_json", side_effect=AssertionError):
            self.assertIsNone(select_goal(self.manifest, "unknown")["selected"])

    def test_qwen_opt_in_fake_returns_candidate_only(self):
        def fake(url, **kwargs):
            self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
            payload = kwargs["payload"]
            self.assertIn("quality", payload["messages"][1]["content"])
            self.assertNotIn('"continue_on_error"', payload["messages"][1]["content"])
            self.assertIn("quality", payload["format"]["properties"]["selected_id"]["enum"])
            return {"message": {"content": '{"version":1,"selected_id":"quality"}'}}
        with patch("eai.goal_selector.fetch_json", side_effect=fake):
            report = select_goal(self.manifest, "please find quality problems",
                                 use_qwen=True)
        self.assertEqual(report["selected"]["id"], "quality")
        self.assertEqual(report["method"], "LOCAL_MODEL_INPUT_ONLY")

    def test_model_unknown_id_fails_closed_to_review(self):
        with patch("eai.goal_selector.fetch_json", return_value={
                "message": {"content": '{"version":1,"selected_id":"root_shell"}'}}):
            report = select_goal(self.manifest, "not literal", use_qwen=True)
        self.assertIsNone(report["selected"])
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertIn("ValueError", report["notice"])

    def test_model_duplicate_json_fields_rejected(self):
        with patch("eai.goal_selector.fetch_json", return_value={
                "message": {"content": '{"version":1,"selected_id":"quality","selected_id":"schedule"}'}}):
            report = select_goal(self.manifest, "not literal", use_qwen=True)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")

    def test_remote_ollama_url_fails_closed(self):
        result = select_goal(self.manifest, "not literal", use_qwen=True,
                             ollama_url="https://outside.example:11434")
        self.assertIsNone(result["selected"])
        self.assertIn("ValueError", result["notice"])

    def test_model_down_fails_to_review_no_retry(self):
        with patch("eai.goal_selector.fetch_json", side_effect=ConnectionError("down")) as called:
            report = select_goal(self.manifest, "not literal", use_qwen=True)
        called.assert_called_once()
        self.assertEqual(report["status"], "REVIEW_REQUIRED")

    def test_no_file_creation_and_no_executing_side_effects(self):
        before = {f.name: f.read_bytes() for f in self.root.iterdir()}
        select_goal(self.manifest, "schedule")
        self.assertEqual(before, {f.name: f.read_bytes() for f in self.root.iterdir()})

    def test_rejects_bad_contract_and_invalid_request(self):
        with self.assertRaises(ValueError):
            select_goal(self.manifest, "")
        self.manifest.write_text('{"kind":"not_a_manifest"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            select_goal(self.manifest, "quality")

    def test_symlink_escape_from_manifest_denied(self):
        with tempfile.TemporaryDirectory() as outer:
            ext = Path(outer) / "private.json"
            ext.write_text('{"version":1,"kind":"csv_quality"}')
            link = self.root / "bad.json"
            try:
                link.symlink_to(ext)
            except (NotImplementedError, OSError):
                self.skipTest("symlink unavailable")
            self.manifest.write_text(json.dumps({
                "version":1,"kind":"goal_batch","continue_on_error":True,
                "items":[{"id":"bad","goal":"bad.json",
                          "sha256":hashlib.sha256(ext.read_bytes()).hexdigest()}]
            }),encoding="utf-8")
            with self.assertRaises(ValueError):
                select_goal(self.manifest,"bad")

    def test_cli_status_success_and_review(self):
        cmd = [sys.executable, "-m", "eai", "select-goal",
               "--manifest", str(self.manifest), "--request"]
        yes = subprocess.run(cmd + ["quality", "--json"], capture_output=True, text=True)
        self.assertEqual(yes.returncode, 0, yes.stderr)
        self.assertEqual(json.loads(yes.stdout)["selected"]["id"], "quality")
        no = subprocess.run(cmd + ["unmentioned", "--json"], capture_output=True, text=True)
        self.assertEqual(no.returncode, 3, no.stderr)


if __name__ == "__main__":
    unittest.main()
