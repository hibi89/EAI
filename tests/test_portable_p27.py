"""P27 source-only reproducible zipapp and CLI smoke on synthetic input."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from scripts.build_portable import build_portable


ROOT = Path(__file__).resolve().parents[1]


class PortableP27Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "eai-portable.pyz"

    def test_build_and_run_version(self):
        report = build_portable(ROOT, self.path)
        self.assertEqual(report["version"], "eai.portable.v1")
        self.assertGreater(report["source_modules"], 20)
        self.assertEqual(report["sha256"],
                         hashlib.sha256(self.path.read_bytes()).hexdigest())
        p = subprocess.run([sys.executable,str(self.path),"--version"],
                           capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_run_health_without_model(self):
        build_portable(ROOT,self.path)
        proc = subprocess.run([sys.executable,str(self.path),"health"],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn("CPU-first", proc.stdout)

    def test_packaged_synthetic_cpu_goal(self):
        build_portable(ROOT,self.path)
        goal = self.folder / "goal.json"
        goal.write_text(json.dumps({
            "version":1,"kind":"schedule_tasks","goal":"Portable test",
            "deadline_hours":"3",
            "tasks":[{"id":"a","hours":"1","requires":[]},
                     {"id":"b","hours":"1","requires":["a"]}]
        }),encoding="utf-8")
        proc = subprocess.run([
            sys.executable,str(self.path),"solve-goal",str(goal),"--json"
        ],capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"],"DECIDED")
        self.assertEqual(result["verification"]["status"],"PASS")

    def test_reproducible_hash_at_two_destinations(self):
        result1 = build_portable(ROOT,self.path)
        result2 = build_portable(ROOT,self.folder/"other.pyz")
        self.assertEqual(result1["sha256"],result2["sha256"])

    def test_existing_file_never_overwritten(self):
        self.path.write_bytes(b"owner backup must remain")
        with self.assertRaises(FileExistsError):
            build_portable(ROOT,self.path)
        self.assertEqual(self.path.read_bytes(),b"owner backup must remain")

    def test_non_pyz_output_rejected(self):
        with self.assertRaises(ValueError):
            build_portable(ROOT,self.folder/"bad.zip")
        self.assertEqual(list(self.folder.iterdir()),[])

    def test_missing_output_parent_rejected(self):
        with self.assertRaises(ValueError):
            build_portable(ROOT,self.folder/"missing"/"eai.pyz")

    def test_zip_contains_only_python_without_secrets(self):
        build_portable(ROOT,self.path)
        with ZipFile(self.path) as archive:
            names = archive.namelist()
            self.assertEqual(archive.testzip(),None)
            self.assertEqual(names[0],"__main__.py")
            self.assertTrue(all(name.endswith(".py") for name in names))
            self.assertTrue(all(name == "__main__.py" or name.startswith("eai/")
                                for name in names))
            self.assertTrue(all(not name.endswith(".env") for name in names))
            self.assertNotIn("tests/test_core.py",names)

    def test_file_symlink_output_refused(self):
        old=self.folder/"existing.pyz"
        old.write_bytes(b"private")
        try:
            self.path.symlink_to(old)
        except (OSError,NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaises(FileExistsError):
            build_portable(ROOT,self.path)
        self.assertEqual(old.read_bytes(),b"private")

    def test_missing_source_root_rejected(self):
        with self.assertRaises((ValueError, OSError)):
            build_portable(self.folder,self.path)

    def test_cli_build_explicit_output(self):
        proc = subprocess.run([
            sys.executable,"scripts/build_portable.py","--source-root",str(ROOT),
            "--output",str(self.path)
        ],cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        report=json.loads(proc.stdout)
        self.assertEqual(report["sha256"],
                         hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_cli_refuses_second_write(self):
        build_portable(ROOT,self.path)
        p=subprocess.run([
            sys.executable,"scripts/build_portable.py","--source-root",str(ROOT),
            "--output",str(self.path)
        ],cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,1)
        self.assertIn("EAI PORTABLE ERROR",p.stderr)


if __name__ == "__main__":
    unittest.main()
