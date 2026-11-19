"""Offline Windows P2-08 measurement script must never launch by default.

Runs a copied Python PE named EAI.exe only as READ-ONLY input; the script
must not execute that binary, open owner profiles, or create a measurement dir.
Real native GUI/IME/DPI/RSS acceptance is NOT_RUN by these probes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure_desktop_windows.ps1"


@unittest.skipUnless(os.name == "nt", "PowerShell Windows preflight only")
class WindowsMeasurementPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="eai-measure-preflight-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "EAI.exe"
        shutil.copyfile(sys.executable, self.binary)

    def invoke(self, binary: Path, *, allow_run: bool = False) -> subprocess.CompletedProcess[str]:
        command = [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Exe", str(binary),
        ]
        if allow_run:
            command.append("-RunWithOwnerConsent")
        return subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20, check=False,
        )

    def test_default_is_read_only_and_does_not_execute_renamed_python(self):
        original = self.binary.read_bytes()
        result = self.invoke(self.binary)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "PREFLIGHT_ONLY")
        self.assertEqual(report["mode"], "READ_ONLY")
        self.assertIs(report["launch_consent"], False)
        self.assertEqual(report["physical_ux_acceptance"], "NOT_RUN")
        self.assertEqual(report["samples"], [])
        self.assertEqual(report["executable_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.binary.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["EAI.exe"])

    def test_wrong_executable_name_is_rejected_before_any_run(self):
        wrong = self.root / "arbitrary.exe"
        shutil.copyfile(self.binary, wrong)
        before = wrong.read_bytes()
        result = self.invoke(wrong)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("MEASURED_REQUIRES_OWNER_REVIEW", result.stdout)
        self.assertEqual(wrong.read_bytes(), before)

    def test_bad_pe_is_rejected_even_with_explicit_run_flag(self):
        self.binary.write_bytes(b"NOT_A_WINDOWS_PE" * 80)
        before = self.binary.read_bytes()
        result = self.invoke(self.binary, allow_run=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("MEASURED_REQUIRES_OWNER_REVIEW", result.stdout)
        self.assertEqual(self.binary.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
