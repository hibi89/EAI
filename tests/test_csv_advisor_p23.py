"""P23 exact-source offline CSV advisor tests; no customer files/network."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.csv_advisor import advise_csv, render_csv_advice


class CsvAdvisorP23Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "metrics.csv"
        self.source.write_text(
            "sales,cost,note\n10,5,first_private_991\n"
            "11,6,b\n12,7,c\n13,8,d\n14,9,e\n15,10,f\n",
            encoding="utf-8"
        )

    def advise(self, **kwargs):
        return advise_csv(self.root, "metrics.csv", **kwargs)

    def test_real_editable_goals_without_execution(self):
        result = self.advise()
        self.assertEqual(result["status"], "DRAFT_READY")
        self.assertEqual([row["kind"] for row in result["drafts"]],
                         ["csv_relationships", "csv_robust_outliers"])
        self.assertEqual(result["drafts"][0]["goal"]["columns"], ["sales", "cost"])
        self.assertEqual(result["drafts"][1]["goal"]["threshold"], "3")
        self.assertIn("NO_AUTO_EXECUTE", result["policy"])
        self.assertEqual(result["source"]["sha256"],
                         hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(result["source"]["rows"], 6)

    def test_no_csv_cell_values_revealed(self):
        report = self.advise()
        self.assertNotIn("first_private_991", json.dumps(report))
        self.assertNotIn("first_private_991", render_csv_advice(report))

    def test_missing_and_bad_numeric_are_counts_only(self):
        self.source.write_text(
            "a,b\n1,10\n2,20\n3,30\n4,40\n5,50\n,not_num\n",
            encoding="utf-8")
        result = self.advise()
        self.assertEqual(result["columns"][0]["numeric_rows"], 5)
        self.assertEqual(result["columns"][0]["missing_rows"], 1)
        self.assertEqual(result["columns"][1]["nonnumeric_rows"], 1)
        self.assertEqual(len(result["drafts"]), 2)

    def test_without_numeric_candidates_review_not_guess(self):
        self.source.write_text("person,city\nalice,seoul\nbob,busan\n", encoding="utf-8")
        result = self.advise()
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["drafts"], [])

    def test_fewer_than_five_numeric_rows_not_proposed(self):
        self.source.write_text("value\n1\n2\n3\n4\n", encoding="utf-8")
        self.assertEqual(self.advise()["drafts"], [])

    def test_zero_record_csv_does_not_claim_ready(self):
        self.source.write_text("a,b\n", encoding="utf-8")
        self.assertEqual(self.advise()["status"], "REVIEW_REQUIRED")

    def test_csv_bad_header_and_broken_width_rejected(self):
        self.source.write_text("a,A\n1,2\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.advise()
        self.source.write_text("a,b\n1\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.advise()

    def test_source_path_traversal_and_absolute_rejected(self):
        for name in ("../metrics.csv", str(self.source), "C:\\data\\x.csv", "x.txt"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                advise_csv(self.root, name)

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outer:
            outside = Path(outer) / "outside.csv"
            outside.write_text("a\n1\n", encoding="utf-8")
            link = self.root / "link.csv"
            try:
                link.symlink_to(outside)
            except (NotImplementedError, OSError):
                self.skipTest("symlink unavailable")
            with self.assertRaises(ValueError):
                advise_csv(self.root, "link.csv")

    def test_invalid_encoding_and_invalid_utf8(self):
        with self.assertRaises(ValueError):
            self.advise(encoding="latin1")
        self.source.write_bytes(b"a\n\xff\n")
        with self.assertRaises(UnicodeError):
            self.advise()

    def test_cp949_explicit_supported(self):
        self.source.write_bytes(("매출,비용\n" +
                                 "\n".join(f"{n},{n+1}" for n in range(6)) +
                                 "\n").encode("cp949"))
        report = self.advise(encoding="cp949")
        self.assertEqual(report["status"], "DRAFT_READY")
        self.assertEqual(report["columns"][0]["header"], "매출")

    def test_mutation_during_scan_is_rejected(self):
        from eai import csv_advisor
        real = csv_advisor.source_snapshot
        calls = [0]
        def raced(path):
            calls[0] += 1
            raw, sha = real(path)
            if calls[0] == 2:
                return raw, "0" * 64
            return raw, sha
        with patch.object(csv_advisor, "source_snapshot", side_effect=raced):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.advise()

    def test_no_external_network_or_file_creation(self):
        before = self.source.read_bytes()
        old_files = set(self.root.iterdir())
        result = self.advise()
        self.assertEqual(before, self.source.read_bytes())
        self.assertEqual(old_files, set(self.root.iterdir()))
        self.assertTrue(all(item["goal"]["source"] == "metrics.csv"
                            for item in result["drafts"]))

    def test_cli_json_and_text(self):
        cmd = [sys.executable, "-m", "eai", "advise-csv",
               "--root", str(self.root), "--source", "metrics.csv"]
        result = subprocess.run(cmd + ["--json"], capture_output=True, text=True,
                                timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["source"]["rows"], 6)
        self.assertNotIn("first_private_991", result.stdout)
        text_result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        self.assertIn("Editable draft kinds:", text_result.stdout)

    def test_cli_failure_fails_closed(self):
        result = subprocess.run(
            [sys.executable, "-m", "eai", "advise-csv",
             "--root", str(self.root), "--source", "../bad.csv", "--json"],
            capture_output=True, text=True, timeout=20
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("EAI ADVISOR ERROR:", result.stderr)


if __name__ == "__main__":
    unittest.main()
