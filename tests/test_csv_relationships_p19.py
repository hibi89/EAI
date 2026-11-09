"""P19 typed multivariate CSV relationship audit and independent evidence tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.csv_relationships import (
    validate_relationship_goal, execute_relationship_goal, render_relationships
)
from eai.relationship_receipt import verify_relationship_receipt
from eai.goal_dispatch import execute_goal_document
from eai.goal_batch import execute_batch_document
from eai.goal_pipeline import execute_pipeline_document


def specification():
    return {
        "version": 1, "kind": "csv_relationships", "goal": "Relationship evidence",
        "source": "records.csv", "encoding": "utf-8-sig",
        "columns": ["x", "y", "z"], "min_rows": 5
    }


LINEAR = "x,y,z,label\n" + "".join(
    f"{i},{i*10},{11-i},SYNTHETIC_SECRET_{i}\n" for i in range(1, 9)
)


def choice():
    return {
        "version": 1, "kind": "choose_options", "goal": "Safe compute choice",
        "criteria": [{"id": "cost", "direction": "min", "unit": "USD",
                      "weight": "1", "score_min": "0", "score_max": "100"}],
        "options": [{"id": "cpu", "values": {"cost": "1"}},
                    {"id": "cloud", "values": {"cost": "5"}}]
    }


class RelationshipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.csv = self.root / "records.csv"
        self.csv.write_text(LINEAR)
        self.goal_file = self.root / "goal.json"
        self.write(specification())

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.goal_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def solve(self, data=None):
        if data is not None:
            self.write(data)
        return execute_goal_document(self.goal_file)

    def test_verified_positive_and_negative_linear_relationships(self):
        report = self.solve()
        self.assertEqual(report["status"], "AGREE")
        self.assertEqual(report["route"], "csv.relationships.v1")
        self.assertEqual(report["verification"]["status"], "PASS")
        self.assertEqual(report["verification"]["diagnostics"]["type"], "NONE")
        result = report["result"]
        self.assertEqual(result["rows"], 8)
        self.assertEqual(result["complete_rows"], 8)
        self.assertEqual([x["coefficient"] for x in result["pairs"]],
                         ["1.000000", "-1.000000", "-1.000000"])
        self.assertEqual(result["pairs"][0]["direction"], "STRONG_POSITIVE")
        self.assertEqual(result["pairs"][1]["direction"], "STRONG_NEGATIVE")
        self.assertIn("CPU 다변량", render_relationships(result))

    def test_unrelated_metric_yields_zero(self):
        self.csv.write_text("x,y,z\n1,2,0\n2,1,0\n3,0,0\n4,1,0\n5,2,0\n")
        data = specification()
        data["columns"] = ["x", "y"]
        r = self.solve(data)
        self.assertEqual(r["status"], "AGREE")
        self.assertEqual(r["result"]["pairs"][0]["coefficient"], "0.000000")
        self.assertEqual(r["result"]["pairs"][0]["direction"], "WEAK_OR_NONE")

    def test_decimal_precision_and_noncausality(self):
        self.csv.write_text(
            "x,y,z\n0.300000000001,10,1\n0.300000000002,20,2\n"
            "0.300000000003,30,3\n0.300000000004,40,4\n"
            "0.300000000005,50,5\n"
        )
        result = self.solve()
        self.assertEqual(result["status"], "AGREE")
        self.assertEqual(result["result"]["pairs"][0]["coefficient"], "1.000000")
        self.assertIn("인과관계", result["result"]["scope"])

    def test_massive_offset_still_has_correct_correlation(self):
        values = [str(10000000000000000000000 + i) for i in range(1, 7)]
        self.csv.write_text("x,y,z\n" + "".join(
            f"{v},{i*2},{i*3}\n" for i, v in enumerate(values, 1)
        ))
        self.assertEqual(self.solve()["result"]["pairs"][0]["coefficient"], "1.000000")

    def test_incomplete_cases_are_explicit_conflict(self):
        self.csv.write_text(
            "x,y,z\n1,2,3\n2,3,4\n3,4,5\n4,5,6\n5,6,7\n"
            "6,,8\n7,NaN,9\n8,12,10\n"
        )
        report = self.solve()
        self.assertEqual(report["status"], "CONFLICT")
        self.assertEqual(report["verification"]["diagnostics"]["type"],
                         "NUMERIC_DATA_REVIEW")
        self.assertEqual(report["result"]["missing_rows"], 1)
        self.assertEqual(report["result"]["invalid_rows"], 1)
        self.assertEqual(report["result"]["complete_rows"], 6)
        self.assertEqual(report["result"]["pairs"][0]["coefficient"], "0.980609")

    def test_missing_precedes_invalid_only_for_fully_numeric_partial(self):
        self.csv.write_text("x,y,z\n" + "".join(
            f"{i},{i*2},{i*3}\n" for i in range(1, 6)
        ) + "6,,hello\n")
        r = self.solve()
        self.assertEqual(r["result"]["missing_rows"], 0)
        self.assertEqual(r["result"]["invalid_rows"], 1)

    def test_all_invalid_is_conflict_without_unsupported_coefficients(self):
        self.csv.write_text("x,y,z\n1,x,1\n2,y,2\n3,z,3\n4,q,4\n5,t,5\n")
        r = self.solve()
        self.assertEqual(r["status"], "CONFLICT")
        self.assertEqual(r["result"]["complete_rows"], 0)
        self.assertTrue(all(p["coefficient"] is None for p in r["result"]["pairs"]))

    def test_few_rows_is_unavailable_not_success(self):
        self.csv.write_text("x,y,z\n1,2,3\n2,3,4\n3,4,5\n4,5,6\n")
        r = self.solve()
        self.assertEqual(r["status"], "UNAVAILABLE")
        self.assertTrue(all(x["direction"] == "NOT_ESTIMABLE"
                            for x in r["result"]["pairs"]))

    def test_zero_variance_denies_unsupported_inference(self):
        self.csv.write_text("x,y,z\n" + "".join(
            f"{i},10,{i*3}\n" for i in range(1, 7)
        ))
        r = self.solve()
        self.assertEqual(r["status"], "UNAVAILABLE")
        self.assertIsNone(r["result"]["pairs"][0]["coefficient"])
        self.assertEqual(r["result"]["pairs"][1]["coefficient"], "1.000000")

    def test_aggregate_only_does_not_leak_any_row_values(self):
        output = json.dumps(self.solve(), ensure_ascii=False)
        self.assertNotIn("SYNTHETIC_SECRET_", output)
        self.assertNotIn("SYNTHETIC_SECRET_5", output)
        self.assertIn("complete_rows", output)

    def test_source_and_goal_file_unchanged(self):
        before = (self.csv.read_bytes(), self.goal_file.read_bytes())
        self.solve()
        self.assertEqual(before, (self.csv.read_bytes(), self.goal_file.read_bytes()))

    def test_cp949_and_bom(self):
        self.csv.write_bytes((
            "x,y,z,설명\n" + "".join(f"{i},{2*i},{3*i},가\n" for i in range(1, 6))
        ).encode("cp949"))
        payload = specification()
        payload["encoding"] = "cp949"
        self.assertEqual(self.solve(payload)["status"], "AGREE")
        payload["encoding"] = "utf-8-sig"
        self.csv.write_text(LINEAR, encoding="utf-8-sig")
        self.assertEqual(self.solve(payload)["status"], "AGREE")

    def test_wrong_json_schema_fails_closed(self):
        for extra in ({"script": "open('secret')"}, {"kind": "shell"},
                      {"version": True}, {"min_rows": "5"},
                      {"min_rows": 4}, {"min_rows": 20001},
                      {"encoding": "latin-1"}, {"columns": ["x"]},
                      {"columns": ["x", "x"]}):
            data = specification()
            data.update(extra)
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.solve(data)

    def test_invalid_column_and_source_fails_closed(self):
        for source in ("../secret.csv", "/tmp/secret.csv",
                       "C:\\user.csv", ".\\records.csv"):
            raw = specification()
            raw["source"] = source
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.solve(raw)
        raw = specification()
        raw["columns"] = ["x", "missing"]
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.solve(raw)

    def test_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            destination = Path(outside) / "remote.csv"
            destination.write_text(LINEAR)
            link = self.root / "link.csv"
            try:
                link.symlink_to(destination)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not available")
            raw = specification()
            raw["source"] = "link.csv"
            with self.assertRaises(ValueError):
                self.solve(raw)

    def test_rejects_invalid_headers_and_malformed_row(self):
        for csv_text in ("x,y,y\n1,2,3\n", "x,X,z\n1,2,3\n",
                         "x,y,z\n1,2\n", "x,y,z\n1,2,3,4\n"):
            self.csv.write_text(csv_text)
            with self.subTest(csv_text=csv_text), self.assertRaises(ValueError):
                self.solve()

    def test_file_size_and_row_limit(self):
        from eai.csv_analysis import MAX_FILE_BYTES
        self.csv.write_text("x,y,z\n" + "a"*(MAX_FILE_BYTES+1))
        with self.assertRaises(ValueError):
            self.solve()
        self.csv.write_text("x,y,z\n" + "1,2,3\n"*20001)
        with self.assertRaisesRegex(ValueError, "bound"):
            self.solve()

    def test_invalid_number_rejected_from_inference(self):
        for invalid in ("inf", "NaN", "1e2", "1_000"):
            self.csv.write_text("x,y,z\n" + "1,2,3\n"*5 +
                                f"5,{invalid},5\n")
            report = self.solve()
            self.assertEqual(report["status"], "CONFLICT")
            self.assertEqual(report["result"]["invalid_rows"], 1)

    def test_forged_evidence_rejected_independently(self):
        orig = specification()
        goal = validate_relationship_goal(orig, self.goal_file)
        legit = execute_relationship_goal(goal)
        self.assertEqual(verify_relationship_receipt(goal, legit)[1]["type"], "NONE")
        for field, alternate in (
            ("status", "UNAVAILABLE"), ("sha256", "a"*64),
            ("pairs", []), ("complete_rows", 0), ("rows", 999)
        ):
            fake = deepcopy(legit)
            fake[field] = alternate
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_relationship_receipt(goal, fake)
        fake = deepcopy(legit)
        fake["pairs"][0]["coefficient"] = "0.999999"
        with self.assertRaises(ValueError):
            verify_relationship_receipt(goal, fake)

    def test_source_mutation_during_scan_is_detected(self):
        from eai.csv_relationships import _parse as orig
        def changing(goal):
            result = orig(goal)
            self.csv.write_text(self.csv.read_text() + "9,99,1,after\n")
            return result
        with patch("eai.csv_relationships._parse", side_effect=changing):
            # Current verifier rejects the solver receipt from the modified file.
            with self.assertRaises(ValueError):
                self.solve()

    def test_cli_codes_positive_review_unavailable_and_error(self):
        root = Path(__file__).resolve().parent.parent
        def call():
            return subprocess.run(
                [sys.executable, "-m", "eai", "solve-goal",
                 str(self.goal_file), "--json"],
                cwd=root, capture_output=True, text=True, timeout=30
            )
        yes = call()
        self.assertEqual(yes.returncode, 0, yes.stderr)
        self.assertEqual(json.loads(yes.stdout)["status"], "AGREE")
        self.csv.write_text(LINEAR + "9,wat,1,secret\n")
        self.assertEqual(call().returncode, 2)
        self.csv.write_text("x,y,z\n1,2,3\n")
        self.assertEqual(call().returncode, 3)
        raw = specification()
        raw["run"] = "shell"
        self.write(raw)
        bad = call()
        self.assertEqual(bad.returncode, 1)
        self.assertNotIn("Traceback", bad.stderr)

    def test_batch_review_and_pipeline_dependency_hold(self):
        self.csv.write_text(LINEAR + "9,NaN,1,secret\n")
        follow = self.root / "choice.json"
        follow.write_text(json.dumps(choice()))
        def entry(ident, path, deps=None):
            raw = {
                "id": ident, "goal": path,
                "sha256": hashlib.sha256((self.root / path).read_bytes()).hexdigest()
            }
            if deps is not None:
                raw["requires"] = deps
            return raw
        first = entry("relationship", "goal.json")
        last = entry("follow", "choice.json")
        batch = self.root / "batch.json"
        batch.write_text(json.dumps({
            "version": 1, "kind": "goal_batch",
            "continue_on_error": True, "items": [first, last]
        }))
        result = execute_batch_document(batch)
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["verification"]["status"], "PASS")
        pipe = self.root / "pipe.json"
        pipe.write_text(json.dumps({
            "version": 1, "kind": "goal_pipeline",
            "continue_on_error": True,
            "items": [dict(first, requires=[]), dict(last, requires=["relationship"])]
        }))
        outcome = execute_pipeline_document(pipe)
        self.assertEqual(outcome["status"], "REVIEW")
        self.assertEqual(outcome["verification"]["status"], "PASS")
        self.assertEqual(outcome["items"][1]["status"], "SKIPPED")
        self.assertEqual(outcome["items"][1]["blocked_by"], ["relationship"])


if __name__ == "__main__":
    unittest.main()
