"""P26 SHA-based explicit owner approval and P23/P24/P15 E2E."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.approved_run import run_approved
from eai.goal_selector import select_goal
from eai.csv_advisor import advise_csv
from eai.manifest_builder import build_goal_manifest


class ApprovedRunP26Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.goal = self.root / "goal.json"
        self.goal.write_text(json.dumps({
            "version":1, "kind":"schedule_tasks", "goal":"Release evidence",
            "deadline_hours":"3",
            "tasks":[{"id":"build","hours":"1","requires":[]},
                     {"id":"qa","hours":"1","requires":["build"]}]
        }), encoding="utf-8")
        self.manifest = self.root / "batch.json"
        self.make_batch()

    def make_batch(self, goal_name="goal.json", kind="goal_batch"):
        self.manifest.write_text(json.dumps({
            "version":1, "kind":kind,"continue_on_error":True,
            "items":[{"id":"release", "goal":goal_name,
                      "sha256":hashlib.sha256(self.goal.read_bytes()).hexdigest(),
                      **({"requires":[]} if kind=="goal_pipeline" else {})}]
        }), encoding="utf-8")

    def select(self):
        result = select_goal(self.manifest, "release")
        return result["manifest"]["sha256"], result["selected"]["sha256"]

    def execute_approved(self):
        manifest_sha, goal_sha = self.select()
        return run_approved(self.manifest, "release", manifest_sha, goal_sha)

    def test_selection_is_not_execution_approval(self):
        item = select_goal(self.manifest, "release")
        self.assertTrue(item["requires_explicit_execution"])
        self.assertFalse("receipt" in item)
        report = self.execute_approved()
        self.assertTrue(report["verified"])
        self.assertEqual(report["receipt"]["verification"]["status"], "PASS")
        self.assertEqual(report["status"], "DECIDED")
        self.assertEqual(report["authorization"]["mode"], "SEPARATE_EXPLICIT_CALL")

    def test_wrong_goal_id_or_sha_rejected(self):
        m, g = self.select()
        with self.assertRaises(ValueError):
            run_approved(self.manifest, "not_a_real_goal", m, g)
        with self.assertRaisesRegex(ValueError, "goal approval"):
            run_approved(self.manifest, "release", m, "0" * 64)
        with self.assertRaisesRegex(ValueError, "manifest approval"):
            run_approved(self.manifest, "release", "0" * 64, g)

    def test_invalid_case_or_bad_digests_rejected(self):
        m, g = self.select()
        for bad in ("not a sha", "A" * 64, "", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run_approved(self.manifest, "release", bad, g)

    def test_goal_bytes_changed_since_selection(self):
        m, g = self.select()
        self.goal.write_text('{"changed":true}',encoding="utf-8")
        with self.assertRaises(ValueError):
            run_approved(self.manifest,"release",m,g)

    def test_manifest_bytes_changed_since_selection(self):
        m, g = self.select()
        self.manifest.write_text(self.manifest.read_text()+" ",encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest approval"):
            run_approved(self.manifest,"release",m,g)

    def test_pipeline_cannot_bypass_dependency_runner(self):
        self.make_batch(kind="goal_pipeline")
        m, g = self.select()
        with self.assertRaisesRegex(ValueError, "pipeline-goals"):
            run_approved(self.manifest,"release",m,g)

    def test_no_auto_retry_on_guard_failure(self):
        m, g = self.select()
        with patch("eai.approved_run.execute_goal_document",
                   return_value={"input":{"sha256":g},
                                 "verification":{"status":"FAILED"}}) as called:
            with self.assertRaisesRegex(ValueError, "verification"):
                run_approved(self.manifest, "release", m, g)
        called.assert_called_once()

    def test_goal_changes_during_solver_fail_closed(self):
        m, g = self.select()
        from eai.goal_dispatch import execute_goal_document
        def mutated(path):
            result = execute_goal_document(path)
            self.goal.write_text(self.goal.read_text()+" ",encoding="utf-8")
            return result
        with patch("eai.approved_run.execute_goal_document", side_effect=mutated):
            with self.assertRaisesRegex(ValueError, "changed"):
                run_approved(self.manifest,"release",m,g)

    def test_full_p23_p15_p24_p26_readonly_path(self):
        csvfile = self.root / "metrics.csv"
        csvfile.write_text("ads,sales\n1,3\n2,6\n3,9\n4,12\n5,15\n6,18\n",
                           encoding="utf-8")
        proposed = advise_csv(self.root,"metrics.csv")
        draft = proposed["drafts"][0]["goal"]
        typed = self.root / "relationship.json"
        typed.write_text(json.dumps(draft),encoding="utf-8")
        manifest_dict = build_goal_manifest("batch",self.root,
                                             ["rel=relationship.json"])
        manifest = self.root / "relationship_manifest.json"
        manifest.write_text(json.dumps(manifest_dict),encoding="utf-8")
        selected = select_goal(manifest,"rel")
        report = run_approved(manifest,"rel",selected["manifest"]["sha256"],
                               selected["selected"]["sha256"])
        self.assertEqual(report["status"],"AGREE")
        self.assertEqual(report["receipt"]["verification"]["status"],"PASS")
        self.assertEqual(csvfile.read_text().count("\n"),7)

    def test_no_network_or_file_creation(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        with patch("eai.goal_selector.fetch_json",side_effect=AssertionError):
            self.execute_approved()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_cli_explicit_approval(self):
        m,g = self.select()
        proc = subprocess.run([
            sys.executable,"-m","eai","run-approved","--manifest",str(self.manifest),
            "--id","release","--manifest-sha256",m,"--goal-sha256",g,"--json"
        ],capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"],"DECIDED")

    def test_cli_wrong_sha_status_one(self):
        m,g = self.select()
        proc = subprocess.run([
            sys.executable,"-m","eai","run-approved","--manifest",str(self.manifest),
            "--id","release","--manifest-sha256",m,"--goal-sha256","0"*64
        ],capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,1)
        self.assertIn("EAI APPROVAL ERROR",proc.stderr)


if __name__ == "__main__":
    unittest.main()
