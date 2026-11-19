"""P2 UX01: actual native-owner draft contract -> local AXNODE comparisons.

This uses typed public APIs, an actual disposable SQLite AXNODE store and
real CPU Architect, not mocked design results. User/customer sources and
operational permissions are never touched.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from eai.contracts import PlanSpec, ProblemSpec
from eai.desktop_bridge import DesktopBridge
from eai.desktop_example import PracticeWorkspace
from eai.desktop_presentation import explain


class P2OwnerGoalToOptionsTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="eai-ux01-private-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bridge = DesktopBridge(self.root)
        practice = PracticeWorkspace()
        self.addCleanup(practice.close)
        self.library = practice.library

    def draft(self):
        goal = "로컬 검토 후보 두 가지를 실제 근거와 비용 기준으로 비교해줘"
        return self.bridge.make_problem_draft(
            goal, domain="practice", risk="LOW", max_steps=8, max_seconds=60)

    def complete(self):
        raw = self.draft()
        raw.update(oracle="owner.local.oracle",
                   state_refs=["synthetic.local.1"],
                   hard_constraints=["forbid:unsafe.operation"],
                   objectives=["검증 가능한 두 경로 비교"],
                   permissions=["pure", "local.read"])
        return raw

    def source_snapshot(self):
        return {str(p.relative_to(self.library)):
                hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.library.rglob("*") if p.is_file()}

    def test_new_korean_goal_reaches_real_distinct_explainable_options(self):
        raw = self.draft()
        self.assertEqual(self.bridge.draft_review(raw)["status"], "REVIEW_REQUIRED")
        self.assertIn("NO_EVIDENCE_REFS", self.bridge.draft_review(raw)["missing"])
        approved = self.complete()
        self.assertEqual(self.bridge.draft_review(approved)["status"],
                         "FORM_COMPLETE_UNVERIFIED")
        digest = ProblemSpec.validate(approved).digest()
        before = self.source_snapshot()
        with patch.object(socket.socket, "connect",
                          side_effect=AssertionError("network denied")):
            discovery = self.bridge.discover_goal_capabilities(approved, self.library)
            hold = self.bridge.architect_reviewed_goal(
                approved, self.library, owner_reviewed=False)
            output = self.bridge.architect_reviewed_goal(
                approved, self.library, owner_reviewed=True)
        self.assertEqual(hold["status"], "HOLD_OWNER_REVIEW_REQUIRED")
        self.assertEqual(discovery["problem_sha256"], digest)
        self.assertEqual(discovery["execution"], "NOT_EXECUTED")
        self.assertEqual(output["status"], "TWO_PLANS_ADVISORY_UNVERIFIED")
        self.assertEqual(output["engine_status"], "CANDIDATES_UNVERIFIED")
        self.assertEqual(output["problem_sha256"], digest)
        self.assertEqual(len(output["plan_specs"]), 2)
        self.assertEqual(len(output["comparison"]), 2)
        self.assertEqual(len(set(map(tuple, output["source_sets"]))), 2)
        self.assertEqual({item["id"] for item in output["comparison"]},
                         set(output["plan_specs"]))
        for alternative_id, spec in output["plan_specs"].items():
            plan = PlanSpec.validate(spec)
            self.assertEqual(plan.problem_sha256, digest)
            entry = next(x for x in output["comparison"]
                         if x["id"] == alternative_id)
            self.assertEqual(entry["source_status"], "LOCAL_CANDIDATE_UNVERIFIED")
            self.assertEqual(entry["independent_accuracy"], "UNKNOWN")
            self.assertGreater(entry["declared_steps"], 0)
            self.assertGreater(entry["declared_seconds_upper_bound"], 0)
            self.assertTrue(entry["evidence_hashes"])
            self.assertTrue(entry["tradeoffs"])
            self.assertTrue(entry["verification_required"])
        human_view = explain("design", output)
        self.assertIn("대안 비교", human_view)
        self.assertIn("자원 상한", human_view)
        self.assertNotIn(approved["goal"], human_view)
        self.assertEqual(self.source_snapshot(), before)
        self.assertFalse((self.root / "drafts").exists())
        self.assertFalse(output["can_execute"])
        self.assertEqual(output["external_actions"], 0)

    def test_incomplete_unsupported_and_conflicted_goal_are_explicit_holds(self):
        before = self.source_snapshot()
        cases = (
            (self.draft(), "HOLD_INCOMPLETE_PROBLEM", "NO_EVIDENCE_REFS"),
            (dict(self.complete(), domain="not_registered"),
             "HOLD_DISTINCT_PLANS_NOT_ESTABLISHED",
             "INSUFFICIENT_DISTINCT_LOCAL_STRATEGIES"),
            (dict(self.complete(), hard_constraints=[
                "must:practice.review", "forbid:practice.review"]),
             "HOLD_DISTINCT_PLANS_NOT_ESTABLISHED",
             "CONTRADICTORY_HARD_CONSTRAINTS"),
        )
        with patch.object(socket.socket, "connect",
                          side_effect=AssertionError("network denied")):
            for raw, status, reason in cases:
                with self.subTest(expected=status, reason=reason):
                    result = self.bridge.architect_reviewed_goal(
                        raw, self.library, owner_reviewed=True)
                    self.assertEqual(result["status"], status)
                    self.assertIn(reason, result["blockers"])
                    self.assertEqual(result["plan_specs"], {})
                    self.assertFalse(result["can_execute"])
                    self.assertEqual(result["external_actions"], 0)
        self.assertEqual(self.source_snapshot(), before)

    def test_nonexistent_explicit_library_and_missing_read_scope_cannot_fabricate_plans(self):
        raw = self.complete()
        for source, expected in (
            (None, "HOLD_LOCAL_LIBRARY_REQUIRED"),
            (self.library, "HOLD_LOCAL_READ_NOT_APPROVED"),
        ):
            changed = raw if source is None else dict(raw, permissions=["pure"])
            result = self.bridge.architect_reviewed_goal(
                changed, source, owner_reviewed=True)
            self.assertEqual(result["status"], expected)
            self.assertEqual(result["plan_specs"], {})
            self.assertFalse(result["can_execute"])
        absent = self.root / "absent-library"
        with self.assertRaises((OSError, ValueError)):
            self.bridge.architect_reviewed_goal(
                raw, absent, owner_reviewed=True)
        self.assertFalse(absent.exists())


if __name__ == "__main__":
    unittest.main()
