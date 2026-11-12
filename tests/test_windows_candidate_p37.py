"""P37: Windows acceptance harness preflight, without claiming Linux is Windows."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from scripts.accept_windows_candidate import accept_windows_candidate, main
from scripts.build_customer_candidate import NAME, build
from scripts.verify_customer_candidate import verify_archive


class WindowsCandidateGateTests(unittest.TestCase):
    def test_ack_required_before_any_files_or_process(self):
        with patch("scripts.accept_windows_candidate._is_windows",
                   side_effect=AssertionError("host check not authorized")), \
             patch("scripts.accept_windows_candidate.build",
                   side_effect=AssertionError("must not build")):
            result = accept_windows_candidate()
        self.assertEqual(result, {"status": "BLOCKED",
                                  "code": "WINDOWS_HOST_ACK_REQUIRED"})

    def test_linux_or_nonwindows_must_not_claim_cmd_pass(self):
        with patch("scripts.accept_windows_candidate._is_windows",
                   return_value=False), \
             patch("scripts.accept_windows_candidate._run_cmd",
                   side_effect=AssertionError("no native CMD")), \
             patch("scripts.accept_windows_candidate.build",
                   side_effect=AssertionError("no build")):
            result = accept_windows_candidate(acknowledge=True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["code"], "NATIVE_WINDOWS_NOT_AVAILABLE")

    def test_cli_requires_windows_ack(self):
        with patch("scripts.accept_windows_candidate._is_windows",
                   side_effect=AssertionError("no access")):
            self.assertEqual(3, main([]))

    def test_canonical_package_roundtrip_remains_source_only(self):
        with TemporaryDirectory() as tmp:
            artifact = Path(tmp) / NAME
            report = build(artifact)
            verified = verify_archive(artifact, Path(tmp) / (NAME + ".sha256"))
        self.assertEqual(report["sha256"], verified["sha256"])
        self.assertIs(report["release_approved"], False)
        self.assertEqual(7, report["files"])

    def test_windows_host_status_always_requires_real_result(self):
        with patch("scripts.accept_windows_candidate._is_windows",
                   return_value=False):
            self.assertNotEqual("PASS", accept_windows_candidate(
                acknowledge=True)["status"])


if __name__ == "__main__":
    unittest.main()
