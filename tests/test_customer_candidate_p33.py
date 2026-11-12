"""P33 real extracted portable EAI customer candidate tests (synthetic only)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from scripts.build_customer_candidate import NAME, build, package_bytes
from scripts.verify_customer_candidate import (CandidateError,
    PREFIX, FILES, verify_archive, verify_directory)

ROOT = Path(__file__).resolve().parents[1]


class CandidatePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="eai-candidate-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / NAME
        self.info = build(self.archive)
        with ZipFile(self.archive) as z:
            z.extractall(self.root / "unpacked")
        self.installed = self.root / "unpacked" / PREFIX.rstrip("/")

    def call(self, *args, expected=0):
        cmd = [sys.executable, "-I", "-B", str(self.installed / "eai.pyz"), *map(str, args)]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=self.root, timeout=50)
        self.assertEqual(expected, proc.returncode, proc.stderr)
        return proc

    def test_reproducible_build_and_declared_payload_only(self):
        self.assertEqual("EAI_REVIEW_CANDIDATE_BUILT_VERIFIED_UNSIGNED",
                         self.info["status"])
        self.assertEqual(7, self.info["files"])
        self.assertEqual(self.archive.read_bytes(), package_bytes())
        self.assertFalse(self.info["release_approved"])
        with ZipFile(self.archive) as z:
            names = z.namelist()
        self.assertEqual(8, len(names))
        self.assertTrue(all(s.startswith(PREFIX) for s in names))
        self.assertFalse(any(".env" in s or "customer" in s.lower() and
                             s.endswith(".csv") for s in names))

    def test_fresh_extract_integrity_verified(self):
        self.assertEqual("CANDIDATE_DIRECTORY_CONSISTENT_UNSIGNED",
                         verify_directory(self.installed)["status"])
        checksum = self.archive.with_name(self.archive.name + ".sha256")
        self.assertEqual(self.info["sha256"],
                         verify_archive(self.archive, checksum)["sha256"])

    def test_real_python_zipapp_cli_and_source_free_report(self):
        self.assertEqual(0, self.call("--version").returncode)
        sample = self.installed / "samples/sample_key_coverage_goal.json"
        solved = json.loads(self.call("solve-goal", sample, "--json").stdout)
        self.assertEqual("AGREE", solved["status"])
        self.assertEqual("PASS", solved["verification"]["status"])
        output = self.root / "customer-review"
        result = json.loads(self.call(
            "customer-review", "--spec", sample, "--output-dir", output,
            "--ack-authorized-local").stdout)
        self.assertEqual("REVIEW_CREATED_UNSIGNED", result["status"])
        self.assertEqual("REVIEW_CONSISTENT_UNSIGNED",
                         json.loads(self.call("verify-review", "--output-dir",
                                              output).stdout)["status"])
        content = (output / "review.json").read_text("utf-8")
        self.assertNotIn("sku_a", content)
        self.assertNotIn("line_1", content)
        self.assertNotIn("item_ref", content)
        self.assertEqual("CANDIDATE_DIRECTORY_CONSISTENT_UNSIGNED",
                         verify_directory(self.installed)["status"])

    def test_repeat_and_missing_consent_refused(self):
        sample = self.installed / "samples/sample_key_coverage_goal.json"
        folder = self.root / "review"
        without = self.call("customer-review", "--spec", sample,
                            "--output-dir", folder, expected=1)
        self.assertIn("LOCAL_SOURCE_ACK_REQUIRED", without.stderr)
        self.assertFalse(folder.exists())
        self.call("customer-review", "--spec", sample, "--output-dir", folder,
                  "--ack-authorized-local")
        repeat = self.call("customer-review", "--spec", sample,
                           "--output-dir", folder, "--ack-authorized-local", expected=1)
        self.assertIn("OUTPUT_ALREADY_EXISTS", repeat.stderr)

    def test_tamper_recipient_bundle_and_package_refused(self):
        sample = self.installed / "samples/sample_key_coverage_goal.json"
        output = self.root / "review"
        self.call("customer-review", "--spec", sample, "--output-dir", output,
                  "--ack-authorized-local")
        (output / "review.html").write_text("tampered", encoding="utf-8")
        denied = self.call("verify-review", "--output-dir", output, expected=1)
        self.assertIn("REVIEW_INTEGRITY_MISMATCH", denied.stderr)
        (self.installed / "eai.pyz").write_bytes(b"tampered program")
        with self.assertRaisesRegex(CandidateError, "DIRECTORY_TAMPERED"):
            verify_directory(self.installed)

    def test_wrong_detached_hash_rejected(self):
        other = self.root / "other.sha256"
        other.write_text("0" * 64 + "  " + NAME + "\n", encoding="ascii")
        with self.assertRaisesRegex(CandidateError, "CHECKSUM_MISMATCH"):
            verify_archive(self.archive, other)

    def test_hidden_zip_prefix_suffix_and_comment_rejected(self):
        # zipfile accepts ordinary ZIP payloads with invisible bytes, even if
        # the caller recomputes the unsigned detached digest.
        from io import BytesIO
        original = self.archive.read_bytes()
        commented = BytesIO(original)
        with ZipFile(commented, "a") as archive:
            archive.comment = b"INVISIBLE-UNDECLARED-CONTENT"
        variants = {
            "prefix": b"MZ" + original,
            "suffix": original + b"UNDECLARED-TRAILER",
            "comment": commented.getvalue(),
        }
        for label, raw in variants.items():
            with self.subTest(label=label):
                candidate = self.root / (label + ".zip")
                candidate.write_bytes(raw)
                with ZipFile(candidate) as archive:
                    self.assertEqual(8, len(archive.namelist()))
                with self.assertRaisesRegex(CandidateError, "ARCHIVE_NONCANONICAL"):
                    verify_archive(candidate)

    def test_package_no_overwrite(self):
        original = self.archive.read_bytes()
        with self.assertRaisesRegex(ValueError, "NEW file"):
            build(self.archive)
        self.assertEqual(original, self.archive.read_bytes())

    def test_windows_runner_contract_static(self):
        runner = (self.installed / "RUN_EAI_REVIEW.cmd").read_text(encoding="utf-8")
        self.assertIn("--ci", runner)
        self.assertIn("verify_candidate.py", runner)
        self.assertIn("customer-review", runner)
        self.assertIn("verify-review", runner)
        self.assertIn("--ack-authorized-local", runner)
        self.assertNotIn("curl ", runner.lower())
        self.assertNotIn("powershell -enc", runner.lower())

    @unittest.skipUnless(os.name == "nt", "hosted Windows runner not enabled for EAI")
    def test_real_windows_cmd_execution_only_if_authorized(self):
        cmd = subprocess.run(["cmd.exe", "/d", "/c",
                               str(self.installed / "RUN_EAI_REVIEW.cmd"), "--ci"],
                             capture_output=True, text=True, timeout=55,
                             cwd=self.root)
        self.assertEqual(0, cmd.returncode, cmd.stdout + cmd.stderr)
        self.assertTrue((self.root / "unpacked" / "EAI-SYNTHETIC-REVIEW" / "review.html").exists())


if __name__ == "__main__":
    unittest.main()
