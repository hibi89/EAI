"""P28 quick commands use existing verified CPU solvers without goal files."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.quick_goal import quick_goal, render_quick


class QuickP28Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / "metrics.csv"
        self.csv.write_text("a,b\n1,3\n2,6\n3,9\n4,12\n5,15\n6,18\n7,21\n",
                            encoding="utf-8")
        self.text = self.root / "memo.md"
        self.text.write_text("risk mitigation planned\nno other evidence\n",
                             encoding="utf-8")

    def relationship(self):
        return quick_goal("csv_relationships",self.root,source="metrics.csv",
                          columns=["a","b"])

    def outlier(self):
        return quick_goal("csv_robust_outliers",self.root,source="metrics.csv",
                          columns=["a"], threshold="3")

    def evidence(self):
        return quick_goal("local_evidence_search",self.root,
                          sources=["memo.md"],terms=["risk","mitigation"])

    def test_relationship_direct_cpu_and_guard(self):
        result=self.relationship()
        self.assertEqual(result["status"],"AGREE")
        self.assertEqual(result["verification"]["status"],"PASS")
        self.assertEqual(result["kind"],"csv_relationships")

    def test_outlier_direct_cpu_and_guard(self):
        result=self.outlier()
        self.assertIn(result["status"],("AGREE","CONFLICT","UNAVAILABLE"))
        self.assertEqual(result["verification"]["status"],"PASS")

    def test_evidence_matches_one_line(self):
        result=self.evidence()
        self.assertEqual(result["status"],"AGREE")
        self.assertEqual(result["result"]["matching_lines"],1)
        self.assertIn("READ_ONLY",render_quick(result))

    def test_default_evidence_snippet_hidden(self):
        result=self.evidence()
        self.assertIsNone(result["result"]["matches"][0]["excerpt"])

    def test_explicit_snippet_opt_in(self):
        result=quick_goal("local_evidence_search",self.root,
                          sources=["memo.md"],terms=["risk"],include_snippets=True)
        self.assertIn("risk mitigation",result["human_report"])

    def test_source_immutable_and_no_goals_written(self):
        before={f.name:f.read_bytes() for f in self.root.iterdir()}
        self.relationship()
        self.outlier()
        self.evidence()
        self.assertEqual(before,{f.name:f.read_bytes() for f in self.root.iterdir()})

    def test_no_model_call_default(self):
        with patch("eai.intent.fetch_json",side_effect=AssertionError):
            self.assertEqual(self.relationship()["status"],"AGREE")

    def test_invalid_kind_or_wrong_mode_args(self):
        with self.assertRaises(ValueError):
            quick_goal("arbitrary_python",self.root)
        with self.assertRaises(ValueError):
            quick_goal("csv_relationships",self.root,source="metrics.csv")
        with self.assertRaises(ValueError):
            quick_goal("local_evidence_search",self.root,sources=["memo.md"],
                       terms=["risk"],threshold="2")

    def test_source_escape_denied(self):
        with self.assertRaises(ValueError):
            quick_goal("csv_relationships",self.root,
                       source="../metrics.csv",columns=["a","b"])

    def test_nonexistent_or_wrong_columns_rejected(self):
        with self.assertRaises(ValueError):
            quick_goal("csv_relationships",self.root,
                       source="metrics.csv",columns=["a","missing"])

    def test_csv_deliberately_bad_values_are_conflict(self):
        self.csv.write_text("a,b\n1,2\n2,3\n3,4\n4,5\n5,6\n6,invalid\n")
        result=self.relationship()
        self.assertEqual(result["status"],"CONFLICT")
        self.assertEqual(result["verification"]["status"],"PASS")

    def test_evidence_no_match_unavailable(self):
        result=quick_goal("local_evidence_search",self.root,
                          sources=["memo.md"],terms=["never_found"])
        self.assertEqual(result["status"],"UNAVAILABLE")

    def test_cli_relationship(self):
        cmd=[sys.executable,"-m","eai","quick-goal","--kind","csv_relationships",
             "--root",str(self.root),"--source","metrics.csv",
             "--columns","a","b","--json"]
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["verification"]["status"],"PASS")

    def test_cli_evidence_text(self):
        cmd=[sys.executable,"-m","eai","quick-goal","--kind","local_evidence_search",
             "--root",str(self.root),"--sources","memo.md",
             "--terms","risk","mitigation"]
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn("로컬 증거 검색",proc.stdout)

    def test_cli_wrong_contract_fails_closed(self):
        cmd=[sys.executable,"-m","eai","quick-goal","--kind","csv_relationships",
             "--root",str(self.root),"--source","../escape.csv",
             "--columns","a","b"]
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,1)
        self.assertIn("EAI QUICK ERROR",proc.stderr)


if __name__ == "__main__":
    unittest.main()
