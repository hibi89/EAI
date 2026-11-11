"""P31 real source-backed relational CSV goal and independent verdict tests."""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from eai.csv_key_coverage import (execute_key_coverage_goal,
    validate_key_coverage_goal)
from eai.goal_dispatch import execute_goal_document
from eai.key_coverage_receipt import verify_key_coverage_receipt

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "sample_key_coverage_goal.json"
MASTER = ROOT / "examples" / "sample_master_keys.csv"
DETAIL = ROOT / "examples" / "sample_detail_keys.csv"


class KeyCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="eai-key-coverage-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = self.root / "master.csv"
        self.detail = self.root / "detail.csv"
        self.master.write_text("item_id,label\na,a\nb,b\nc,c\n", encoding="utf-8")
        self.detail.write_text("line,item_ref\n1,a\n2,a\n3,c\n", encoding="utf-8")
        self.raw = {
            "version": 1, "kind": "csv_key_coverage",
            "goal": "Synthetic referential integrity",
            "master": "master.csv", "detail": "detail.csv",
            "master_key": "item_id", "detail_key": "item_ref",
            "encoding": "utf-8-sig", "min_coverage_percent": "100",
        }
        self.spec = self.root / "goal.json"
        self.save()

    def save(self):
        self.spec.write_text(json.dumps(self.raw, ensure_ascii=False),
                             encoding="utf-8")

    def solve(self):
        self.save()
        return execute_goal_document(self.spec)

    def test_approved_synthetic_sample_in_repository(self):
        result = execute_goal_document(SAMPLE)
        self.assertEqual("AGREE", result["status"])
        self.assertEqual("PASS", result["verification"]["status"])
        self.assertEqual("csv.key_coverage.v1", result["route"])
        self.assertEqual(13, len(__import__("eai.goal_dispatch", fromlist=["ROUTED_KINDS"]).ROUTED_KINDS))

    def test_happy_path_duplicate_child_references_allowed(self):
        report = self.solve()
        self.assertEqual("AGREE", report["status"])
        self.assertEqual(0, report["result"]["detail_missing_reference_rows"])
        self.assertEqual(3, report["result"]["detail_matched_rows"])
        self.assertEqual("100.000000", report["result"]["coverage_percent"])
        self.assertEqual({"type": "NONE", "action_required": False},
                         report["verification"]["diagnostics"])

    def test_orphans_above_threshold_fail_closed(self):
        self.detail.write_text("line,item_ref\n1,a\n2,missing\n3,c\n", encoding="utf-8")
        self.assertEqual("CONFLICT", self.solve()["status"])
        self.assertEqual("66.666667", self.solve()["result"]["coverage_percent"])
        self.assertEqual("RELATIONAL_INTEGRITY_REVIEW",
                         self.solve()["verification"]["diagnostics"]["type"])

    def test_orphans_with_lower_threshold_still_conflict(self):
        self.detail.write_text("line,item_ref\n1,a\n2,missing\n3,c\n", encoding="utf-8")
        self.raw["min_coverage_percent"] = "60"
        report = self.solve()
        self.assertEqual("CONFLICT", report["status"])
        self.assertTrue(report["result"]["coverage_threshold_met"])
        self.assertEqual(1, report["result"]["detail_missing_reference_rows"])
        self.assertNotIn("2,missing", json.dumps(report["result"]))

    def test_rounding_not_silently_passing_threshold(self):
        self.detail.write_text("line,item_ref\n1,a\n2,missing\n3,c\n", encoding="utf-8")
        self.raw["min_coverage_percent"] = "66.6666668"
        report = self.solve()
        self.assertEqual("CONFLICT", report["status"])
        self.assertFalse(report["result"]["coverage_threshold_met"])

    def test_master_duplicates_and_blanks(self):
        self.master.write_text("item_id,label\na,a\na,b\n,blank\n", encoding="utf-8")
        result = self.solve()
        self.assertEqual("CONFLICT", result["status"])
        self.assertEqual(1, result["result"]["master_duplicate_rows"])
        self.assertEqual(1, result["result"]["master_empty_key_rows"])

    def test_detail_missing_keys(self):
        self.detail.write_text("line,item_ref\n1,a\n2,\n3,c\n", encoding="utf-8")
        result = self.solve()
        self.assertEqual("CONFLICT", result["status"])
        self.assertEqual(1, result["result"]["detail_empty_key_rows"])

    def test_empty_master_unavailable_without_detail(self):
        self.master.write_text("item_id,label\n", encoding="utf-8")
        self.detail.write_text("line,item_ref\n", encoding="utf-8")
        self.assertEqual("UNAVAILABLE", self.solve()["status"])

    def test_no_valid_detail_keys_unavailable(self):
        self.detail.write_text("line,item_ref\n", encoding="utf-8")
        self.assertEqual("UNAVAILABLE", self.solve()["status"])

    def test_orphans_with_no_master_trigger_conflict(self):
        self.master.write_text("item_id,label\n", encoding="utf-8")
        result = self.solve()
        self.assertEqual("CONFLICT", result["status"])

    def test_forged_receipts_rejected(self):
        goal = validate_key_coverage_goal(self.raw, self.spec)
        original = execute_key_coverage_goal(goal)
        for field, value in (("detail_matched_rows", 20),
                             ("status", "CONFLICT"),
                             ("coverage_percent", "99.999999"),
                             ("master_duplicate_rows", 1),
                             ("coverage_threshold_met", False),
                             ("scope", "certified")):
            with self.subTest(field=field):
                forged = copy.deepcopy(original)
                forged[field] = value
                with self.assertRaisesRegex(ValueError, "independently disagrees"):
                    verify_key_coverage_receipt(goal, forged)

    def test_goal_tamper_and_unknown_fields_rejected(self):
        for key, val in (("version", True), ("kind", "unknown"),
                         ("min_coverage_percent", 100), ("goal", ""),
                         ("encoding", "iso-8859-1")):
            with self.subTest(key=key):
                modified = dict(self.raw, **{key: val})
                with self.assertRaises(ValueError):
                    validate_key_coverage_goal(modified, self.spec)
        changed = dict(self.raw, private_payload="do-not-import")
        with self.assertRaises(ValueError):
            validate_key_coverage_goal(changed, self.spec)

    def test_bad_threshold_or_key_columns_rejected(self):
        for raw in ("-1", "101", "NaN", "Infinity", "false"):
            with self.subTest(raw=raw):
                x = dict(self.raw, min_coverage_percent=raw)
                with self.assertRaises(ValueError):
                    validate_key_coverage_goal(x, self.spec)
        self.raw["master_key"] = "UNKNOWN"
        with self.assertRaises(ValueError):
            self.solve()

    def test_absolute_traversal_and_same_file_refused(self):
        for supplied in ("../outside.csv", "/etc/passwd", "C:\\secret.csv",
                         "sub/../../master.csv", "master.txt"):
            with self.subTest(source=supplied):
                self.raw["master"] = supplied
                with self.assertRaises(ValueError):
                    validate_key_coverage_goal(self.raw, self.spec)
        self.raw["master"] = "master.csv"
        self.raw["detail"] = "master.csv"
        with self.assertRaisesRegex(ValueError, "distinct"):
            validate_key_coverage_goal(self.raw, self.spec)

    def test_symlink_source_refused(self):
        alias = self.root / "alias.csv"
        try:
            alias.symlink_to(self.master)
        except (OSError, NotImplementedError):
            self.skipTest("OS symlink privilege unavailable")
        self.raw["master"] = "alias.csv"
        with self.assertRaisesRegex(ValueError, "linked/reparse"):
            validate_key_coverage_goal(self.raw, self.spec)

    def test_bad_header_duplicate_case_and_row_width(self):
        for broken in ("item_id,ITEM_ID\na,a\n", "item_id,label\na\n",
                       "item_id,label\na,b,c\n", "item_id,label\n\x00,b\n"):
            with self.subTest(broken=broken):
                self.master.write_text(broken, encoding="utf-8")
                with self.assertRaises((ValueError, csv.Error)):
                    self.solve()

    def test_unmodified_sources_and_no_external_paths(self):
        original = (self.master.read_bytes(), self.detail.read_bytes())
        result = self.solve()
        self.assertEqual(original, (self.master.read_bytes(), self.detail.read_bytes()))
        self.assertNotIn("a,a", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(["goal.json"], sorted(p.name for p in self.root.glob("*.json")))

    def test_source_change_blocks_independent_guard(self):
        goal = validate_key_coverage_goal(self.raw, self.spec)
        result = execute_key_coverage_goal(goal)
        self.master.write_text(self.master.read_text() + "d,delta\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "independently disagrees"):
            verify_key_coverage_receipt(goal, result)

    def test_python_cli_isolated_no_side_effect(self):
        cmd = [sys.executable, "-I", "-B", "-m", "eai", "solve-goal", str(SAMPLE), "--json"]
        # Python -I isolates site paths, so -m eai depends on installed package.
        # The portable zipapp uses -I directly in the packaged acceptance test.
        cmd = [sys.executable, "-m", "eai", "solve-goal", str(SAMPLE), "--json"]
        run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual("PASS", json.loads(run.stdout)["verification"]["status"])


if __name__ == "__main__":
    unittest.main()
