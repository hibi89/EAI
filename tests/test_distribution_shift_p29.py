"""P29 two-cohort distribution shift: strict read-only independent CPU proofs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy

from eai.goal_dispatch import execute_goal_document
from eai.csv_distribution_shift import validate_shift_goal, execute_shift_goal, render_shift
from eai.distribution_shift_receipt import verify_shift_receipt


def goal():
    return {
        "version":1,"kind":"csv_distribution_shift",
        "goal":"Inspect business cohort change",
        "baseline":"before.csv","current":"after.csv",
        "encoding":"utf-8-sig","columns":["amount"],
        "min_rows":5,"threshold":"2"
    }


class ShiftP29Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.before=self.root/"before.csv"
        self.after=self.root/"after.csv"
        self.before.write_text("amount\n"+"\n".join(str(v) for v in range(1,12))+"\n")
        self.after.write_text("amount\n"+"\n".join(str(v) for v in range(1,12))+"\n")
        self.spec=self.root/"shift.json"
        self.write(goal())

    def write(self, obj):
        self.spec.write_text(json.dumps(obj),encoding="utf-8")

    def run_goal(self):
        return execute_goal_document(self.spec)

    def test_stable_cohorts_agree_with_guard(self):
        result=self.run_goal()
        self.assertEqual(result["status"],"AGREE")
        self.assertEqual(result["verification"]["status"],"PASS")
        self.assertEqual(result["result"]["columns"][0]["shift_mad_units"],"0.000000")
        self.assertEqual(result["route"],"csv.distribution_shift.v1")

    def test_median_shift_conflict(self):
        self.after.write_text("amount\n"+"\n".join(str(v+20) for v in range(1,12))+"\n")
        result=self.run_goal()
        self.assertEqual(result["status"],"CONFLICT")
        self.assertEqual(result["result"]["columns"][0]["state"],"SHIFT")
        self.assertEqual(result["verification"]["diagnostics"]["type"],"SHIFT_REVIEW")

    def test_baseline_zero_mad_unavailable(self):
        self.before.write_text("amount\n"+"3\n"*10)
        result=self.run_goal()
        self.assertEqual(result["status"],"UNAVAILABLE")
        self.assertEqual(result["result"]["columns"][0]["state"],"NOT_ESTIMABLE")

    def test_missing_or_nonnumeric_conflict_not_imputed(self):
        self.after.write_text("amount\n1\n2\n3\n4\n5\n6\nbad\n")
        result=self.run_goal()
        self.assertEqual(result["status"],"CONFLICT")
        self.assertEqual(result["result"]["sources"][1]["invalid_rows"],1)

    def test_insufficient_samples_unavailable(self):
        self.after.write_text("amount\n1\n2\n3\n")
        result=self.run_goal()
        self.assertEqual(result["status"],"UNAVAILABLE")

    def test_independent_receipt_rejects_forged_score(self):
        spec=validate_shift_goal(goal(),self.spec)
        report=execute_shift_goal(spec)
        forged=deepcopy(report)
        forged["columns"][0]["shift_mad_units"]="10.000000"
        with self.assertRaises(ValueError):
            verify_shift_receipt(spec,forged)

    def test_independent_receipt_rejects_forged_status(self):
        spec=validate_shift_goal(goal(),self.spec)
        report=execute_shift_goal(spec)
        report["status"]="CONFLICT"
        with self.assertRaises(ValueError):
            verify_shift_receipt(spec,report)

    def test_source_hashes_match_original_and_files_unchanged(self):
        original0=self.before.read_bytes()
        original1=self.after.read_bytes()
        result=self.run_goal()
        self.assertEqual(result["result"]["sources"][0]["sha256"],
                         hashlib.sha256(original0).hexdigest())
        self.assertEqual(original0,self.before.read_bytes())
        self.assertEqual(original1,self.after.read_bytes())

    def test_non_ascii_no_values_printed(self):
        self.before.write_text("매출\n"+"\n".join(str(v) for v in range(1,10))+"\n")
        self.after.write_text("매출\n"+"\n".join(str(v) for v in range(1,10))+"\n")
        raw=goal()
        raw["columns"]=["매출"]
        self.write(raw)
        result=self.run_goal()
        self.assertEqual(result["status"],"AGREE")
        self.assertNotIn("private_customer_value",render_shift(result["result"]))

    def test_invalid_path_and_extra_field(self):
        bad=goal()
        bad["baseline"]="../private.csv"
        self.write(bad)
        with self.assertRaises(ValueError):
            self.run_goal()
        bad=goal()
        bad["shell"]="run"
        self.write(bad)
        with self.assertRaises(ValueError):
            self.run_goal()

    def test_same_source_rejected(self):
        bad=goal()
        bad["current"]="before.csv"
        self.write(bad)
        with self.assertRaises(ValueError):
            self.run_goal()

    def test_duplicate_or_unknown_column_rejected(self):
        bad=goal()
        bad["columns"]=["amount","Amount"]
        self.write(bad)
        with self.assertRaises(ValueError):
            self.run_goal()
        bad=goal()
        bad["columns"]=["missing"]
        self.write(bad)
        with self.assertRaises(ValueError):
            self.run_goal()

    def test_invalid_threshold_and_min_rows(self):
        bad=goal()
        bad["threshold"]="0.1"
        self.write(bad)
        with self.assertRaises(ValueError):
            self.run_goal()
        bad=goal()
        bad["min_rows"]=True
        self.write(bad)
        with self.assertRaises(ValueError):
            self.run_goal()

    def test_malformed_csv_row_is_rejected(self):
        self.before.write_text("amount\n1,2\n")
        with self.assertRaises(ValueError):
            self.run_goal()

    def test_cli_conflict_exit_and_verified_receipt(self):
        self.after.write_text("amount\n"+"\n".join(str(v+20) for v in range(1,12))+"\n")
        p=subprocess.run([sys.executable,"-m","eai","solve-goal",str(self.spec),"--json"],
                         capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertEqual(json.loads(p.stdout)["verification"]["status"],"PASS")

    def test_cli_agree_exit(self):
        p=subprocess.run([sys.executable,"-m","eai","solve-goal",str(self.spec),"--json"],
                         capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr)


if __name__=="__main__":
    unittest.main()
