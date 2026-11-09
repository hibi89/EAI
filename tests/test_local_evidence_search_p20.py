"""P20 independent read-only local TXT/Markdown evidence index and receipts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.goal_dispatch import execute_goal_document
from eai.local_evidence_search import (
    validate_search_goal, execute_search_goal, render_search
)
from eai.evidence_search_receipt import verify_search_receipt
from eai.goal_batch import execute_batch_document
from eai.goal_pipeline import execute_pipeline_document


def spec():
    return {
        "version": 1, "kind": "local_evidence_search",
        "goal": "Locate documented local risk evidence",
        "sources": ["a.md", "b.txt"],
        "terms": ["Risk", "Mitigation"], "max_results": 5,
        "include_snippets": False
    }


TEXT_A = (
    "# Evidence\n"
    "Risk mitigation planned. Private_Owner_Name_7383\n"
    "Risk is acknowledged.\n"
    "Mitigation is independent.\n"
    "Risk mitigation risk mitigation.\n"
)
TEXT_B = (
    "Legal standards are unverified.\n"
    "mitigation for RISK is pending.\n"
    "No source found.\n"
)


class LocalEvidenceSearchP20Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "a.md").write_text(TEXT_A, encoding="utf-8")
        (self.root / "b.txt").write_text(TEXT_B, encoding="utf-8")
        self.goal = self.root / "search.json"
        self.write(spec())

    def tearDown(self):
        self.temp.cleanup()

    def write(self, obj):
        self.goal.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def run_goal(self, obj=None):
        if obj is not None:
            self.write(obj)
        return execute_goal_document(self.goal)

    def test_verified_search_ranks_repeat_and_phrase(self):
        result = self.run_goal()
        self.assertEqual(result["status"], "AGREE")
        self.assertEqual(result["route"], "local.evidence_search.v1")
        self.assertEqual(result["verification"]["status"], "PASS")
        findings = result["result"]
        self.assertEqual(findings["matching_lines"], 3)
        self.assertEqual([(m["filename"], m["line"], m["score"])
                          for m in findings["matches"]],
                         [("a.md", 5, 9), ("a.md", 2, 7), ("b.txt", 2, 2)])
        self.assertEqual(findings["sources"][0]["lines"], 5)
        self.assertIn("로컬 증거 검색", render_search(findings))

    def test_no_snippet_default_and_hashes(self):
        output = self.run_goal()
        self.assertNotIn("Private_Owner_Name_7383", json.dumps(output))
        self.assertTrue(all(m["excerpt"] is None
                            for m in output["result"]["matches"]))
        self.assertEqual(output["result"]["sources"][0]["sha256"],
                         hashlib.sha256((self.root / "a.md").read_bytes()).hexdigest())

    def test_explicit_snippet_opt_in_local_only(self):
        obj = spec()
        obj["include_snippets"] = True
        result = self.run_goal(obj)
        self.assertIn("Private_Owner_Name_7383", json.dumps(result))
        self.assertIn("Private_Owner_Name_7383", render_search(result["result"]))
        self.assertEqual(result["verification"]["status"], "PASS")

    def test_unmatched_search_is_unavailable(self):
        obj = spec()
        obj["terms"] = ["nonexistent_794"]
        result = self.run_goal(obj)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["result"]["matching_lines"], 0)
        self.assertEqual(result["result"]["matches"], [])
        self.assertEqual(result["verification"]["diagnostics"]["type"],
                         "NO_EXACT_EVIDENCE")

    def test_terms_across_different_lines_do_not_match(self):
        (self.root / "b.txt").write_text("risk\nmitigation\n")
        (self.root / "a.md").write_text("risk\nmitigation\n")
        self.assertEqual(self.run_goal()["status"], "UNAVAILABLE")

    def test_max_results_and_source_priority(self):
        obj = spec()
        obj["max_results"] = 1
        out = self.run_goal(obj)
        self.assertEqual(len(out["result"]["matches"]), 1)
        self.assertEqual(out["result"]["matching_lines"], 3)
        self.assertEqual(out["result"]["matches"][0]["line"], 5)

    def test_selected_file_order_changes_ties_only(self):
        (self.root / "a.md").write_text("risk mitigation\n")
        (self.root / "b.txt").write_text("risk mitigation\n")
        obj = spec()
        obj["sources"] = ["b.txt", "a.md"]
        result = self.run_goal(obj)
        self.assertEqual([item["filename"] for item in result["result"]["matches"]],
                         ["b.txt", "a.md"])

    def test_non_ascii_casefold_and_utf8_bom(self):
        (self.root / "a.md").write_text("서울 위험 해결방안\n",
                                         encoding="utf-8-sig")
        obj = spec()
        obj["sources"] = ["a.md"]
        obj["terms"] = ["위험", "해결방안"]
        self.assertEqual(self.run_goal(obj)["status"], "AGREE")

    def test_punctuation_is_not_substring_match(self):
        (self.root / "a.md").write_text("risky mitigation\n")
        (self.root / "b.txt").write_text("risk mitigation\n")
        result = self.run_goal()
        self.assertEqual(result["result"]["matching_lines"], 1)
        self.assertEqual(result["result"]["matches"][0]["filename"], "b.txt")

    def test_rejects_extra_instruction_or_nonbool_and_nonint(self):
        for extra in (
            {"command": "delete everything"}, {"kind": "shell"}, {"version": True},
            {"include_snippets": 1}, {"max_results": True}, {"max_results": 0},
            {"max_results": 21}, {"terms": []}, {"terms": ["x"]*6},
            {"terms": ["RISK", "risk"]}, {"terms": ["risk script()"]},
            {"sources": []}, {"sources": ["a.md"]*2}
        ):
            obj = spec()
            obj.update(extra)
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.run_goal(obj)

    def test_rejects_parent_absolute_windows_path_and_extension(self):
        for path in ("../secret.md", "/tmp/private.md", "C:\\secret.md",
                     ".\\a.md", "private.py", "b.csv"):
            obj = spec()
            obj["sources"] = [path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_goal(obj)

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            target = Path(other) / "private.txt"
            target.write_text(TEXT_A)
            link = self.root / "out.txt"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("no symlink capability")
            obj = spec()
            obj["sources"] = ["out.txt"]
            with self.assertRaises(ValueError):
                self.run_goal(obj)

    def test_malformed_utf8_or_binary_rejected(self):
        for data in (b"foo\x00risk mitigation", b"\xff\xfebad"):
            (self.root / "a.md").write_bytes(data)
            with self.assertRaises((ValueError, UnicodeError)):
                self.run_goal()

    def test_rejects_large_and_long_line(self):
        (self.root / "a.md").write_bytes(b"X" * (256*1024+1))
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            self.run_goal()
        (self.root / "a.md").write_text("risk mitigation " + "a" * 2002)
        with self.assertRaisesRegex(ValueError, "line or character"):
            self.run_goal()

    def test_rejects_too_many_lines(self):
        (self.root / "a.md").write_text("risk mitigation\n" * 5001)
        with self.assertRaisesRegex(ValueError, "line or character"):
            self.run_goal()

    def test_files_unchanged_after_search(self):
        prior = [(self.root / name).read_bytes()
                 for name in ("a.md", "b.txt", "search.json")]
        self.run_goal()
        self.assertEqual(prior, [(self.root / name).read_bytes()
                                 for name in ("a.md", "b.txt", "search.json")])

    def test_forged_receipt_detected_independently(self):
        validated = validate_search_goal(spec(), self.goal)
        report = execute_search_goal(validated)
        checks, diag = verify_search_receipt(validated, report)
        self.assertIn("independent_rank", checks)
        self.assertEqual(diag["type"], "NONE")
        for field, fake in [
            ("status", "UNAVAILABLE"), ("matching_lines", 2),
            ("sources", []), ("matches", []), ("include_snippets", True)
        ]:
            tampered = deepcopy(report)
            tampered[field] = fake
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_search_receipt(validated, tampered)
        tampered = deepcopy(report)
        tampered["matches"][0]["line"] = 123
        with self.assertRaises(ValueError):
            verify_search_receipt(validated, tampered)

    def test_change_between_solver_and_verifier_fails(self):
        from eai.local_evidence_search import execute_search_goal as original
        def changing(goal):
            report = original(goal)
            (self.root / "a.md").write_text(TEXT_A + "alteration\n")
            return report
        with patch("eai.goal_dispatch.execute_search_goal", side_effect=changing):
            with self.assertRaisesRegex(ValueError, "receipt"):
                self.run_goal()

    def test_cli_agree_and_unavailable_and_error(self):
        project_root = Path(__file__).resolve().parent.parent
        def call():
            return subprocess.run(
                [sys.executable, "-m", "eai", "solve-goal",
                 str(self.goal), "--json"],
                cwd=project_root, capture_output=True, text=True, timeout=30
            )
        ok = call()
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["verification"]["status"], "PASS")
        obj = spec()
        obj["terms"] = ["noresults"]
        self.write(obj)
        notfound = call()
        self.assertEqual(notfound.returncode, 3, notfound.stderr)
        self.write(dict(obj, malicious_command="shutdown"))
        error = call()
        self.assertEqual(error.returncode, 1)
        self.assertNotIn("Traceback", error.stderr)

    def test_batch_and_pipeline_dependency_hold(self):
        obj = spec()
        obj["terms"] = ["unseen"]
        self.write(obj)
        other = self.root / "choice.json"
        other.write_text(json.dumps({
            "version": 1, "kind": "choose_options", "goal": "select",
            "criteria": [{"id": "cost", "direction": "min",
                          "unit": "USD", "weight": "1",
                          "score_min": "0", "score_max": "100"}],
            "options": [{"id": "A", "values": {"cost": "10"}},
                        {"id": "B", "values": {"cost": "20"}}]
        }))
        def entry(ident, filename, deps=None):
            out = {"id": ident, "goal": filename,
                   "sha256": hashlib.sha256((self.root / filename).read_bytes()).hexdigest()}
            if deps is not None:
                out["requires"] = deps
            return out
        first = entry("proof", "search.json")
        second = entry("next", "choice.json")
        batch = self.root / "batch.json"
        batch.write_text(json.dumps({
            "version": 1, "kind": "goal_batch", "continue_on_error": True,
            "items": [first, second]
        }))
        report = execute_batch_document(batch)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["verification"]["status"], "PASS")
        pipe = self.root / "pipeline.json"
        pipe.write_text(json.dumps({
            "version": 1, "kind": "goal_pipeline", "continue_on_error": True,
            "items": [dict(first, requires=[]), dict(second, requires=["proof"])]
        }))
        output = execute_pipeline_document(pipe)
        self.assertEqual(output["status"], "REVIEW")
        self.assertEqual(output["verification"]["status"], "PASS")
        self.assertEqual(output["items"][1]["status"], "SKIPPED")


if __name__ == "__main__":
    unittest.main()
