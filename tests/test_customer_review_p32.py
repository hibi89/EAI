"""P32 owner-local result bundle: real source, tamper, no-overwrite and privacy tests."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from eai.customer_review import (CustomerReviewError, create_review,
                                 verify_review, render_report_html)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples/sample_key_coverage_goal.json"


class CustomerReviewTests(unittest.TestCase):
    def test_source_backed_review_generated_and_independent_verifier(self):
        with TemporaryDirectory(prefix="eai-review-") as tmp:
            out = Path(tmp) / "new-review"
            before = SAMPLE.read_bytes()
            response = create_review(SAMPLE, out, acknowledge=True)
            self.assertEqual("REVIEW_CREATED_UNSIGNED", response["status"])
            self.assertEqual("AGREE", response["decision_status"])
            self.assertEqual(before, SAMPLE.read_bytes())
            self.assertEqual({"review.json", "review.html", "manifest.json"},
                             {p.name for p in out.iterdir()})
            verification = verify_review(out)
            self.assertEqual("REVIEW_CONSISTENT_UNSIGNED", verification["status"])
            self.assertFalse(verification["origin_authenticated"])
            self.assertFalse(verification["source_reopened"])
            body = (out / "review.html").read_text("utf-8")
            self.assertIn("default-src &#39;none&#39;", body)
            self.assertNotIn("<script", body)
            self.assertNotIn("sku_a", body)
            self.assertNotIn("line_1", body)

    def test_requires_ack_and_no_silent_output(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "not-created"
            with self.assertRaisesRegex(CustomerReviewError, "LOCAL_SOURCE_ACK_REQUIRED"):
                create_review(SAMPLE, out)
            self.assertFalse(out.exists())

    def test_output_refuses_overwrite_and_keeps_original(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "existing"
            out.mkdir()
            marker = out / "keep.txt"
            marker.write_text("my data", encoding="utf-8")
            with self.assertRaisesRegex(CustomerReviewError, "OUTPUT_ALREADY_EXISTS"):
                create_review(SAMPLE, out, acknowledge=True)
            self.assertEqual("my data", marker.read_text("utf-8"))

    def test_tampered_html_rejected(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "review"
            create_review(SAMPLE, out, acknowledge=True)
            (out / "review.html").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(CustomerReviewError, "REVIEW_INTEGRITY_MISMATCH"):
                verify_review(out)

    def test_tampered_json_rejected(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "review"
            create_review(SAMPLE, out, acknowledge=True)
            js = json.loads((out / "review.json").read_text("utf-8"))
            js["status"] = "DECIDED"
            (out / "review.json").write_text(json.dumps(js), encoding="utf-8")
            with self.assertRaisesRegex(CustomerReviewError, "REVIEW_INTEGRITY_MISMATCH"):
                verify_review(out)

    def test_extra_or_missing_files_rejected(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "review"
            create_review(SAMPLE, out, acknowledge=True)
            (out / "unexpected.txt").write_text("raw", encoding="utf-8")
            with self.assertRaisesRegex(CustomerReviewError, "INCOMPLETE_OR_EXTRA_FILES"):
                verify_review(out)
            (out / "unexpected.txt").unlink()
            (out / "manifest.json").unlink()
            with self.assertRaisesRegex(CustomerReviewError, "INCOMPLETE_OR_EXTRA_FILES"):
                verify_review(out)

    def test_incomplete_marker_cannot_pass(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "review"
            create_review(SAMPLE, out, acknowledge=True)
            (out / ".EAI_INCOMPLETE").write_text("cannot trust", encoding="utf-8")
            with self.assertRaisesRegex(CustomerReviewError, "INCOMPLETE_OR_EXTRA_FILES"):
                verify_review(out)

    def test_linked_input_or_output_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            try:
                source.symlink_to(SAMPLE)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privileges unavailable")
            with self.assertRaisesRegex(CustomerReviewError, "LINKED_PATH_REFUSED"):
                create_review(source, root / "new", acknowledge=True)
            out = root / "review"
            create_review(SAMPLE, out, acknowledge=True)
            (out / "review.html").unlink()
            (out / "review.html").symlink_to(SAMPLE)
            with self.assertRaisesRegex(CustomerReviewError, "LINKED_PATH_REFUSED"):
                verify_review(out)

    def test_duplicate_key_manifest_refused(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "review"
            create_review(SAMPLE, out, acknowledge=True)
            (out / "manifest.json").write_text(
                '{"schema_version":1,"schema_version":2}', encoding="utf-8")
            with self.assertRaisesRegex(CustomerReviewError, "DUPLICATE_JSON_KEY"):
                verify_review(out)

    def test_customer_review_cli_and_redacted_error(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "review"
            cmd = [sys.executable, "-m", "eai", "customer-review",
                   "--spec", str(SAMPLE), "--output-dir", str(out)]
            denied = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                                    text=True, timeout=25)
            self.assertEqual(1, denied.returncode)
            self.assertIn("LOCAL_SOURCE_ACK_REQUIRED", denied.stderr)
            self.assertFalse(out.exists())
            approved = subprocess.run(cmd + ["--ack-authorized-local"], cwd=ROOT,
                                      capture_output=True, text=True, timeout=25)
            self.assertEqual(0, approved.returncode, approved.stderr)
            confirmed = subprocess.run(
                [sys.executable, "-m", "eai", "verify-review", "--output-dir", str(out)],
                cwd=ROOT, capture_output=True, text=True, timeout=25)
            self.assertEqual(0, confirmed.returncode, confirmed.stderr)
            self.assertIn("REVIEW_CONSISTENT_UNSIGNED", confirmed.stdout)

    def test_unapproved_spec_unknown_kind_does_not_create_bundle(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "unsupported.json"
            spec.write_text('{"version":1,"kind":"raw_shell","source":"no"}',
                            encoding="utf-8")
            output = root / "review"
            with self.assertRaisesRegex(CustomerReviewError, "SOURCE_REVIEW_REJECTED"):
                create_review(spec, output, acknowledge=True)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
