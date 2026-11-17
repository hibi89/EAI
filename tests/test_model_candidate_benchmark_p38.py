"""P38 offline comparison boundary: synthetic, no model/network or execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.benchmark_model_candidates import compare


class ModelCandidateBenchmarkP38(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        goals = (("choose", "choose_options"), ("schedule", "schedule_tasks"))
        items = []
        for name, kind in goals:
            p = self.root / (name + ".json")
            p.write_text(json.dumps({"version": 1, "kind": kind}), encoding="utf-8")
            items.append({"id": name, "goal": p.name,
                          "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
        self.manifest = self.root / "batch.json"
        self.manifest.write_text(json.dumps({"version": 1, "kind": "goal_batch",
                                             "continue_on_error": True, "items": items}),
                                 encoding="utf-8")
        self.cases = self.root / "cases.json"
        self.predictions = self.root / "predictions.json"
        self.save(self.cases, {"version": 1, "cases": [
            {"id": "c1", "request": "please choose", "expected_id": "choose"},
            {"id": "c2", "request": "please schedule", "expected_id": "schedule"},
            {"id": "c3", "request": "unrelated request", "expected_id": ""},
        ]})
        self.save(self.predictions, {"version": 1, "predictions": [
            {"model": "fixture_hydrogen", "case_id": "c1",
             "raw_output": '{"version":1,"selected_id":"choose"}'},
            {"model": "fixture_hydrogen", "case_id": "c2",
             "raw_output": '{"version":1,"selected_id":"invalid_shell"}'},
            {"model": "fixture_qwen", "case_id": "c1",
             "raw_output": '{"version":1,"selected_id":"choose"}'},
        ]})

    def save(self, path, content):
        path.write_text(json.dumps(content), encoding="utf-8")

    def run_eval(self):
        return compare(self.manifest, self.cases, self.predictions)

    def test_baseline_and_models_separate_and_redacted(self):
        report = self.run_eval()
        self.assertEqual(report["cpu_literal"]["correct"], 3)
        self.assertEqual(report["models"]["fixture_hydrogen"]["invalid"], 1)
        self.assertEqual(report["models"]["fixture_hydrogen"]["missing"], 1)
        self.assertEqual(report["models"]["fixture_qwen"]["missing"], 2)
        self.assertNotIn("unrelated request", json.dumps(report))
        self.assertIn("NO_NETWORK", report["privacy"])

    def test_unknown_id_is_invalid_not_executable(self):
        report = self.run_eval()
        self.assertEqual(report["models"]["fixture_hydrogen"]["correct"], 1)
        self.assertEqual(report["models"]["fixture_hydrogen"]["invalid"], 1)

    def test_duplicate_model_response_rejected(self):
        doc = json.loads(self.predictions.read_text())
        doc["predictions"].append(doc["predictions"][0])
        self.save(self.predictions, doc)
        with self.assertRaisesRegex(ValueError, "duplicate model"):
            self.run_eval()

    def test_duplicate_json_keys_inside_model_response_are_invalid(self):
        doc = json.loads(self.predictions.read_text())
        doc["predictions"][0]["raw_output"] = '{"version":1,"selected_id":"choose","selected_id":"schedule"}'
        self.save(self.predictions, doc)
        self.assertEqual(self.run_eval()["models"]["fixture_hydrogen"]["invalid"], 2)

    def test_goal_tampering_denied_before_scoring(self):
        (self.root / "choose.json").write_text('{"kind":"unknown"}')
        with self.assertRaises(ValueError):
            self.run_eval()

    def test_case_without_approved_truth_denied(self):
        doc = json.loads(self.cases.read_text())
        doc["cases"][0]["expected_id"] = "run_shell"
        self.save(self.cases, doc)
        with self.assertRaisesRegex(ValueError, "unapproved"):
            self.run_eval()

    def test_duplicate_case_denied(self):
        doc = json.loads(self.cases.read_text())
        doc["cases"].append(doc["cases"][0])
        self.save(self.cases, doc)
        with self.assertRaisesRegex(ValueError, "invalid case"):
            self.run_eval()

    def test_files_remain_unchanged(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.run_eval()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_cli_exit_success_and_non_leaking_failure(self):
        cmd = [sys.executable, "-m", "scripts.benchmark_model_candidates",
               "--manifest", str(self.manifest), "--cases", str(self.cases),
               "--predictions", str(self.predictions)]
        ok = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["cases"], 3)
        self.predictions.write_text('{"version":1,"predictions": [],"predictions":[]}')
        bad = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn("unrelated request", bad.stderr)

    def test_no_network_paths_in_benchmark(self):
        with patch("socket.socket", side_effect=AssertionError("network used")):
            self.run_eval()


if __name__ == "__main__":
    unittest.main()
