"""P25 source/receipt-verified HTML/JSON exporter tests."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.report_export import build_report, render_report_html


def goal_json():
    return {
        "version":1, "kind":"schedule_tasks", "goal":"<img src=x onerror=alert(1)>",
        "deadline_hours":"3",
        "tasks":[{"id":"build","hours":"1","requires":[]},
                 {"id":"review","hours":"1","requires":["build"]}]
    }


class ReportExportP25Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.goal = self.root / "goal.json"
        self.goal.write_text(json.dumps(goal_json()), encoding="utf-8")

    def manifest(self, pipeline=False):
        name = "goal_pipeline" if pipeline else "goal_batch"
        entry = {
            "id":"task", "goal":"goal.json",
            "sha256":hashlib.sha256(self.goal.read_bytes()).hexdigest()
        }
        if pipeline:
            entry["requires"] = []
        path = self.root / "manifest.json"
        path.write_text(json.dumps({
            "version":1, "kind":name, "continue_on_error":True,
            "items":[entry]
        }), encoding="utf-8")
        return path

    def test_single_verified_without_raw_goal_text(self):
        summary = build_report(self.goal)
        self.assertEqual(summary["status"], "DECIDED")
        self.assertEqual(summary["verification"], "PASS")
        self.assertEqual(summary["items"][0]["verification"], "PASS")
        self.assertEqual(summary["document"]["sha256"],
                         hashlib.sha256(self.goal.read_bytes()).hexdigest())
        self.assertNotIn("onerror", json.dumps(summary))

    def test_single_html_is_static_with_csp(self):
        page = render_report_html(build_report(self.goal))
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("default-src &#39;none&#39;", page)
        self.assertNotIn("<script", page.lower())
        self.assertNotIn("onerror", page)
        self.assertIn("DECIDED", page)

    def test_html_escapes_untrusted_metadata(self):
        summary = build_report(self.goal)
        summary["document"]["filename"] = '<svg onload="evil()">'
        page = render_report_html(summary)
        self.assertIn("&lt;svg", page)
        self.assertNotIn('<svg onload=', page)

    def test_batch_summary_without_values(self):
        source = self.manifest()
        summary = build_report(source)
        self.assertEqual(summary["kind"], "goal_batch")
        self.assertEqual(summary["status"], "COMPLETE")
        self.assertEqual(summary["items"][0]["id"], "task")
        self.assertEqual(summary["items"][0]["kind"], "schedule_tasks")

    def test_pipeline_summary(self):
        source = self.manifest(pipeline=True)
        summary = build_report(source)
        self.assertEqual(summary["kind"], "goal_pipeline")
        self.assertEqual(summary["status"], "COMPLETE")
        self.assertEqual(summary["items"][0]["verification"], "PASS")

    def test_changed_child_sha_is_rejected_or_error_hold(self):
        source = self.manifest()
        self.goal.write_text('{"version":1}',encoding="utf-8")
        with self.assertRaises(ValueError):
            build_report(source)

    def test_unknown_root_kind_rejected(self):
        self.goal.write_text('{"kind":"run_python"}',encoding="utf-8")
        with self.assertRaises(ValueError):
            build_report(self.goal)

    def test_missing_file_rejected(self):
        with self.assertRaises((OSError, ValueError)):
            build_report(self.root / "missing.json")

    def test_unverified_summary_cannot_render(self):
        with self.assertRaises(ValueError):
            render_report_html({"version":"eai.safe_export.v1", "verification":"NOT_RUN"})

    def test_file_original_untouched_and_no_output_file(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        build_report(self.goal)
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_cli_html_and_json_stdout_only(self):
        base = [sys.executable, "-m", "eai", "export-report",
                str(self.goal), "--format"]
        html = subprocess.run(base + ["html"], capture_output=True, text=True, timeout=20)
        self.assertEqual(html.returncode, 0, html.stderr)
        self.assertIn("<!doctype html>", html.stdout)
        data = subprocess.run(base + ["json"], capture_output=True, text=True, timeout=20)
        self.assertEqual(data.returncode, 0, data.stderr)
        self.assertEqual(json.loads(data.stdout)["verification"], "PASS")
        self.assertEqual(set(self.root.iterdir()), {self.goal})

    def test_cli_bad_input_failure(self):
        result = subprocess.run(
            [sys.executable, "-m", "eai", "export-report", str(self.root/"missing"),
             "--format", "json"], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn("EAI EXPORT ERROR",result.stderr)


if __name__ == "__main__":
    unittest.main()
