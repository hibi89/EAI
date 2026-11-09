"""P22 robust MAD anomalies from owner-selected local CSV, with independent guard."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.csv_robust_outliers import (
    validate_outlier_goal, execute_outlier_goal, render_outliers
)
from eai.outlier_receipt import verify_outlier_receipt
from eai.goal_dispatch import execute_goal_document
from eai.goal_batch import execute_batch_document
from eai.goal_pipeline import execute_pipeline_document


def spec():
    return {
        "version": 1, "kind": "csv_robust_outliers", "goal": "Local anomalies",
        "source": "metrics.csv", "encoding": "utf-8-sig",
        "columns": ["revenue", "expenses"],
        "min_rows": 5, "threshold": "3"
    }


SAMPLE = (
    "id,revenue,expenses,note\n"
    "A,10,1,Private_Ana_9284\n"
    "B,11,3,private\n"
    "C,9,2,private\n"
    "D,10,5,private\n"
    "E,12,4,private\n"
    "F,100,6,private\n"
)
CLEAN = (
    "id,revenue,expenses\n"
    "A,1,1\nB,2,3\nC,3,2\nD,4,5\nE,5,4\nF,6,6\n"
)


class RobustOutlierP22Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "metrics.csv"
        self.source.write_text(SAMPLE, encoding="utf-8")
        self.goal = self.root / "outliers.json"
        self.write(spec())

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, obj):
        self.goal.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def run_goal(self, obj=None):
        if obj is not None:
            self.write(obj)
        return execute_goal_document(self.goal)

    def test_outlier_detected_with_independent_evidence(self):
        result = self.run_goal()
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["route"], "csv.robust_outliers.v1")
        self.assertEqual(result["verification"]["status"], "PASS")
        report = result["result"]
        self.assertEqual(report["rows"], 6)
        self.assertEqual(report["complete_rows"], 6)
        self.assertEqual(report["profiles"][0]["median"], "10.5")
        self.assertEqual(report["profiles"][0]["mad"], "1")
        self.assertEqual(report["profiles"][0]["outliers"], 1)
        self.assertEqual(report["profiles"][1]["outliers"], 0)
        self.assertEqual(report["samples"], [{"record": 6, "column": "revenue"}])
        self.assertIn("MAD", render_outliers(report))

    def test_clean_variability_is_agree(self):
        self.source.write_text(CLEAN)
        r = self.run_goal()
        self.assertEqual(r["status"], "AGREE")
        self.assertEqual(r["result"]["samples"], [])

    def test_threshold_changes_result_without_edits(self):
        # A moderately high non-extreme point is above threshold=3 but not 20.
        self.source.write_text(SAMPLE.replace("F,100,6", "F,20,6"))
        obj = spec()
        obj["threshold"] = "20"
        r = self.run_goal(obj)
        self.assertEqual(r["status"], "AGREE")
        self.assertEqual(r["result"]["profiles"][0]["outliers"], 0)

    def test_zero_mad_is_unavailable_not_zero_anomalies_claim(self):
        self.source.write_text("id,revenue,expenses\n" +
                               "".join(f"{i},10,7\n" for i in range(6)))
        r = self.run_goal()
        self.assertEqual(r["status"], "UNAVAILABLE")
        self.assertTrue(all(x["mad"] == "0" for x in r["result"]["profiles"]))
        self.assertTrue(all(x["estimable"] is False for x in r["result"]["profiles"]))

    def test_few_rows_and_header_only_unavailable(self):
        for rows in ("A,1,3\nB,2,4\n", ""):
            self.source.write_text("id,revenue,expenses\n" + rows)
            result = self.run_goal()
            self.assertEqual(result["status"], "UNAVAILABLE")
            self.assertTrue(all(x["median"] is None
                                for x in result["result"]["profiles"]))

    def test_missing_and_bad_values_fail_closed(self):
        self.source.write_text(
            CLEAN + "G,,7\nH,NaN,8\n"
        )
        result = self.run_goal()
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["result"]["missing_rows"], 1)
        self.assertEqual(result["result"]["invalid_rows"], 1)
        self.assertEqual(result["verification"]["diagnostics"]["type"],
                         "OUTLIER_OR_INPUT_REVIEW")

    def test_high_precision_decimal_is_stable(self):
        values = [
            "10000000000000000000000." + str(i).zfill(12)
            for i in (1,2,3,4,5,100)
        ]
        self.source.write_text("id,revenue,expenses\n" + "".join(
            f"{i},{value},{j}\n" for j, (i,value) in enumerate(
                zip("ABCDEF",values),1)
        ))
        obj = spec()
        obj["columns"] = ["revenue"]
        r = self.run_goal(obj)
        self.assertEqual(r["status"], "CONFLICT")
        self.assertEqual(r["result"]["samples"], [{"record": 6, "column": "revenue"}])

    def test_negative_numbers_and_cp949_encoding(self):
        self.source.write_bytes((
            "id,revenue,expenses,note\n" +
            "".join(f"{i},{-(i+1)},{i+1},서울\n" for i in range(6))
        ).encode("cp949"))
        obj = spec()
        obj["encoding"] = "cp949"
        r = self.run_goal(obj)
        self.assertEqual(r["status"], "AGREE")

    def test_private_cell_values_never_emitted(self):
        serialized = json.dumps(self.run_goal(), ensure_ascii=False)
        self.assertNotIn("Private_Ana_9284", serialized)
        self.assertNotIn("private", serialized)

    def test_original_bytes_untouched(self):
        saved = (self.source.read_bytes(), self.goal.read_bytes())
        self.run_goal()
        self.assertEqual(saved, (self.source.read_bytes(), self.goal.read_bytes()))

    def test_invalid_action_and_number_contract_rejected(self):
        for extra in (
            {"command": "exec"}, {"version": True}, {"kind": "shell"},
            {"threshold": 4}, {"threshold": "0.5"}, {"threshold": "21"},
            {"threshold": "NaN"}, {"threshold": "1e2"}, {"min_rows": True},
            {"min_rows": 4}, {"columns": []}, {"columns": ["revenue"]*2},
            {"encoding": "latin-1"}
        ):
            obj = spec()
            obj.update(extra)
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.run_goal(obj)

    def test_rejects_unknown_or_duplicate_headers(self):
        obj = spec()
        obj["columns"] = ["wrong"]
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.run_goal(obj)
        for text in (
            "id,revenue,Revenue\n1,2,3\n",
            "id,revenue,revenue\n1,2,3\n",
            "id,revenue,expenses\n1,2\n",
            "id,revenue,expenses\n1,2,3,4\n"
        ):
            self.source.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.run_goal()

    def test_path_traversal_and_windows_path_denied(self):
        for path in ("../private.csv", "/tmp/private.csv", "C:\\Private.csv",
                     ".\\metrics.csv"):
            obj = spec()
            obj["source"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_goal(obj)

    def test_rejects_symlink_outside(self):
        with tempfile.TemporaryDirectory() as other:
            remote = Path(other) / "remote.csv"
            remote.write_text(SAMPLE)
            link = self.root / "escape.csv"
            try:
                link.symlink_to(remote)
            except (OSError, NotImplementedError):
                self.skipTest("cannot create symlink")
            obj = spec()
            obj["source"] = "escape.csv"
            with self.assertRaises(ValueError):
                self.run_goal(obj)

    def test_size_and_row_bounds(self):
        self.source.write_bytes(b"x" * (5*1024*1024+1))
        with self.assertRaises(ValueError):
            self.run_goal()
        self.source.write_text("id,revenue,expenses\n" + "A,2,3\n"*20001)
        with self.assertRaisesRegex(ValueError, "limit"):
            self.run_goal()

    def test_forged_evidence_rejected(self):
        goal = validate_outlier_goal(spec(), self.goal)
        valid = execute_outlier_goal(goal)
        checks, diag = verify_outlier_receipt(goal, valid)
        self.assertIn("independent_mad", checks)
        self.assertEqual(diag["type"], "OUTLIER_OR_INPUT_REVIEW")
        for field, forged in (
            ("status", "AGREE"), ("sha256", "0"*64), ("rows", 99),
            ("samples", []), ("columns", []), ("threshold", "10")
        ):
            altered = deepcopy(valid)
            altered[field] = forged
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_outlier_receipt(goal, altered)
        altered = deepcopy(valid)
        altered["profiles"][0]["median"] = "0"
        with self.assertRaises(ValueError):
            verify_outlier_receipt(goal, altered)

    def test_change_between_solver_and_receipt_is_blocked(self):
        from eai.csv_robust_outliers import execute_outlier_goal as real
        def change(goal):
            out = real(goal)
            self.source.write_text(SAMPLE + "G,7,7,more\n")
            return out
        with patch("eai.goal_dispatch.execute_outlier_goal", side_effect=change):
            with self.assertRaises(ValueError):
                self.run_goal()

    def test_cli_success_conflict_empty_invalid(self):
        root = Path(__file__).resolve().parent.parent
        def call():
            return subprocess.run(
                [sys.executable, "-m", "eai", "solve-goal",
                 str(self.goal), "--json"],
                cwd=root, capture_output=True, text=True, timeout=30
            )
        bad = call()
        self.assertEqual(bad.returncode, 2, bad.stderr)
        self.source.write_text(CLEAN)
        self.assertEqual(call().returncode, 0)
        self.source.write_text("id,revenue,expenses\n")
        self.assertEqual(call().returncode, 3)
        obj = spec()
        obj["execute"] = "shell"
        self.write(obj)
        invalid = call()
        self.assertEqual(invalid.returncode, 1)
        self.assertNotIn("Traceback", invalid.stderr)

    def test_batch_pipeline_hold_on_outliers(self):
        choice = self.root / "choice.json"
        choice.write_text(json.dumps({
            "version":1,"kind":"choose_options","goal":"Choice",
            "criteria":[{"id":"cost","direction":"min","unit":"USD",
                         "weight":"1","score_min":"0","score_max":"100"}],
            "options":[{"id":"A","values":{"cost":"1"}},
                       {"id":"B","values":{"cost":"2"}}]
        }))
        def entry(ident, file, requires=None):
            out = {"id":ident,"goal":file,
                   "sha256":hashlib.sha256((self.root / file).read_bytes()).hexdigest()}
            if requires is not None:
                out["requires"] = requires
            return out
        first = entry("audit", "outliers.json")
        second = entry("follow", "choice.json")
        batch = self.root / "batch.json"
        batch.write_text(json.dumps({
            "version":1,"kind":"goal_batch","continue_on_error":True,
            "items":[first,second]
        }))
        outcome = execute_batch_document(batch)
        self.assertEqual(outcome["status"], "REVIEW")
        self.assertEqual(outcome["verification"]["status"], "PASS")
        pipeline = self.root / "pipe.json"
        pipeline.write_text(json.dumps({
            "version":1,"kind":"goal_pipeline","continue_on_error":True,
            "items":[dict(first,requires=[]),
                     dict(second,requires=["audit"])]
        }))
        receipt = execute_pipeline_document(pipeline)
        self.assertEqual(receipt["status"], "REVIEW")
        self.assertEqual(receipt["verification"]["status"], "PASS")
        self.assertEqual(receipt["items"][1]["status"], "SKIPPED")


if __name__ == "__main__":
    unittest.main()
