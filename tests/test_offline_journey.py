"""Integration safety: real Architect -> resource gate -> policy -> pure Player.

All input fixtures are disposable, private-free and CPU/no-network only.
Running these tests does NOT prove customer operations or real-world truth.
"""
from __future__ import annotations

from dataclasses import replace
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from eai.__main__ import main
from eai.axnode_store import AXNodeStore
from eai.architect_runtime import preview_architecture
from eai.local_scheduler import LocalResourceBudget
from eai.offline_journey import preview_offline_journey


class OfflineJourneyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.axnode_dir = self.root / "axnodes"
        self.problem_file = self.root / "problem.json"
        self.problem = {
            "version": 1, "id": "synthetic.journey",
            "goal": "PRIVATE goal never printed", "domain": "data",
            "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["accuracy"],
            "oracle": "synthetic.oracle", "permissions": ["local.read"],
            "budget": {"max_steps": 3, "max_seconds": 60}, "risk": "LOW",
        }
        self.problem_file.write_text(json.dumps(self.problem), encoding="utf-8")
        self.build_nodes()

    @staticmethod
    def node(name: str, skill: str) -> dict:
        return {
            "schema": "eai.axnode.v1", "id": name, "version": 1,
            "kind": "strategy", "status": "CANDIDATE",
            "signature": {"inputs": {"csv": "csv_ref"},
                          "output": "difference_receipt"},
            "pre": ["synthetic_only"], "post": ["requires_independent_review"],
            "steps": [{"skill": skill}],
            "capabilities": [
                "pure" if skill == "synthetic.noop.v1" else "local.read"
            ],
            "parent_hashes": [],
            "tests": {"unit": [], "heldout": [], "negative": []},
            "evidence": [], "provenance": {
                "author": "eai_fixture", "source": "synthetic_only"
            },
            "budget": {"max_steps": 1, "max_seconds": 15},
        }

    def build_nodes(self, skill: str = "csv.reconcile.v1"):
        with AXNodeStore(self.axnode_dir) as store:
            for name in ("data.first", "data.second"):
                store.import_node(json.dumps(self.node(name, skill)))

    def call(self, *, interpret: bool = False, budget=None):
        return preview_offline_journey(
            self.problem_file, self.axnode_dir,
            interpret_pure_noop=interpret, budget=budget)

    def test_full_cpu_architect_policy_blocks_local_file_operators(self):
        with (patch.object(socket, "socket",
                           side_effect=AssertionError("network")),
              patch("eai.local_scheduler.observe_own_process_rss_bytes",
                    return_value=100 * 1024 * 1024)):
            report = self.call(interpret=True)
        self.assertEqual(report["architect_status"], "CANDIDATES_UNVERIFIED")
        self.assertEqual(report["candidate_count"], 2)
        self.assertTrue(all(item["status"] == "POLICY_OR_RESOURCE_HELD"
                            for item in report["candidates"]))
        self.assertTrue(all("REAL_OR_UNSUPPORTED_OPERATOR_BLOCKED" in
                            item["reason_codes"] for item in report["candidates"]))
        self.assertEqual(report["real_tool_invocations"], 0)
        self.assertEqual(report["original_writes"], 0)
        self.assertEqual(report["live_provider_invocations"], 0)
        self.assertFalse(report["active_promotion"])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_noop_pure_executes_only_after_explicit_opt_in(self):
        alt = self.root / "pure_nodes"
        with AXNodeStore(alt) as store:
            for name in ("data.first", "data.second"):
                store.import_node(json.dumps(
                    self.node(name, "synthetic.noop.v1")))
        self.problem["permissions"] = ["pure"]
        self.problem_file.write_text(json.dumps(self.problem), encoding="utf-8")
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=100 * 1024 * 1024):
            preview = preview_offline_journey(
                self.problem_file, alt, interpret_pure_noop=False)
            result = preview_offline_journey(
                self.problem_file, alt, interpret_pure_noop=True)
            again = preview_offline_journey(
                self.problem_file, alt, interpret_pure_noop=True)
        self.assertEqual(preview["candidate_count"], 2)
        self.assertTrue(all(c["status"] == "PURE_ELIGIBLE_NOT_INTERPRETED"
                            for c in preview["candidates"]))
        self.assertTrue(all(c["status"] ==
                            "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED"
                            for c in result["candidates"]))
        self.assertTrue(all(c["interpreted_steps"] == 1 and
                            len(c["trace_sha256"]) == 64
                            for c in result["candidates"]))
        self.assertEqual(result, again)
        self.assertNotEqual(result["receipt_sha256"], preview["receipt_sha256"])
        self.assertFalse(result["verified_real_world"])

    def test_missing_rss_blocks_interpretation_not_current_source(self):
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=None):
            result = self.call(interpret=True)
        self.assertEqual(result["candidate_count"], 2)
        self.assertTrue(all("REAL_RSS_NOT_ESTABLISHED" in c["reason_codes"]
                            for c in result["candidates"]))
        self.assertTrue(all(c["trace_sha256"] is None
                            for c in result["candidates"]))

    def test_too_small_cpu_budget_holds_before_any_action(self):
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=100 * 1024 * 1024):
            result = self.call(
                interpret=True, budget=LocalResourceBudget(
                    max_rss_mib=128, max_elapsed_ms=500, max_steps=1))
        self.assertTrue(all(
            "DECLARED_PLAN_BUDGET_EXCEEDS_CPU_POLICY" in c["reason_codes"]
            for c in result["candidates"]))
        self.assertEqual(result["original_writes"], 0)

    def test_measured_architect_latency_can_hold_pure_interpretation(self):
        from eai.offline_journey import preview_offline_journey
        pure = self.root / "timed_pure_nodes"
        with AXNodeStore(pure) as store:
            for name in ("data.first", "data.second"):
                store.import_node(json.dumps(self.node(name, "synthetic.noop.v1")))
        self.problem["permissions"] = ["pure"]
        self.problem_file.write_text(json.dumps(self.problem), encoding="utf-8")
        with (patch("eai.offline_journey.monotonic_ns",
                    side_effect=[0, 61_000_000_000, 62_000_000_000]),
              patch("eai.local_scheduler.observe_own_process_rss_bytes",
                    return_value=100 * 1024 * 1024)):
            report = preview_offline_journey(
                self.problem_file, pure, interpret_pure_noop=True,
                budget=LocalResourceBudget(max_rss_mib=128,
                                           max_elapsed_ms=60000,
                                           max_steps=64))
        self.assertTrue(all(c["status"] == "POLICY_OR_RESOURCE_HELD"
                            for c in report["candidates"]))
        self.assertTrue(all("TIME_BUDGET_EXCEEDED" in c["reason_codes"]
                            for c in report["candidates"]))
        self.assertEqual(report["real_tool_invocations"], 0)

    def test_tampered_step_source_is_rejected(self):
        original = preview_architecture(self.problem_file, self.axnode_dir)
        changed = dict(original)
        changed["advisory_plans"] = [
            dict(option) for option in original["advisory_plans"]]
        altered = changed["advisory_plans"][0]
        altered["step_sources"] = [{"step": "step01",
                                    "axnode_sha256": "a" * 64}]
        with patch("eai.offline_journey.preview_architecture",
                   return_value=changed):
            with self.assertRaisesRegex(ValueError, "pinned"):
                self.call()

    def test_forged_operator_is_not_laundered_by_valid_axnode_sha(self):
        self.problem["permissions"] = ["local.read", "pure"]
        self.problem_file.write_text(json.dumps(self.problem), encoding="utf-8")
        source = preview_architecture(self.problem_file, self.axnode_dir)
        changed = dict(source)
        changed["advisory_plans"] = [dict(item) for item in source["advisory_plans"]]
        first = changed["advisory_plans"][0]
        first["plan_steps"] = [dict(step) for step in first["plan_steps"]]
        first["plan_steps"][0]["operator"] = "synthetic.noop.v1"
        first["plan_steps"][0]["capability"] = "pure"
        with patch("eai.offline_journey.preview_architecture", return_value=changed):
            with self.assertRaisesRegex(ValueError, "not bound to pinned"):
                self.call(interpret=True)

    def test_forged_capability_cannot_claim_pure_local_read(self):
        source = preview_architecture(self.problem_file, self.axnode_dir)
        changed = dict(source)
        changed["advisory_plans"] = [dict(item) for item in source["advisory_plans"]]
        first = changed["advisory_plans"][0]
        first["plan_steps"] = [dict(step) for step in first["plan_steps"]]
        first["plan_steps"][0]["capability"] = "pure"
        with patch("eai.offline_journey.preview_architecture", return_value=changed):
            with self.assertRaisesRegex(ValueError, "not bound to pinned"):
                self.call(interpret=True)

    def test_high_risk_architect_is_hold_not_unsafe_player(self):
        self.problem["risk"] = "HIGH"
        self.problem_file.write_text(json.dumps(self.problem), encoding="utf-8")
        result = self.call(interpret=True)
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["architect_status"], "BLOCKED")
        self.assertEqual(result["real_tool_invocations"], 0)

    def test_research_optional_on_never_changes_off_candidates(self):
        from eai.research_policy import ResearchMode, ResearchPolicy
        on = ResearchPolicy(
            mode=ResearchMode.RESEARCH_OPT_IN,
            external_sends_approved=True, free_tier_verified=True)
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=100 * 1024 * 1024):
            off = self.call(interpret=False)
            from eai.offline_journey import preview_offline_journey
            attempted = preview_offline_journey(
                self.problem_file, self.axnode_dir,
                research_policy=on)
        self.assertEqual(off["research_mode_status"], "OFF")
        self.assertEqual(attempted["research_mode_status"], "PAUSED_POLICY")
        self.assertEqual(off["candidates"], attempted["candidates"])
        self.assertEqual(attempted["research_candidates_admitted"], 0)
        self.assertEqual(attempted["live_provider_invocations"], 0)

    def test_manually_forged_research_policy_type_is_rejected(self):
        from eai.offline_journey import preview_offline_journey
        with self.assertRaises(ValueError):
            preview_offline_journey(
                self.problem_file, self.axnode_dir,
                research_policy=object())

    def test_report_digest_audit_never_grants_execution(self):
        from eai.offline_journey import audit_offline_journey_report
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=100 * 1024 * 1024):
            report = self.call(interpret=True)
        reviewed = audit_offline_journey_report(report)
        self.assertEqual(reviewed["status"],
                         "LOCAL_JOURNEY_DIGEST_INTEGRITY_UNVERIFIED")
        self.assertEqual(reviewed["candidate_count"], 2)
        self.assertFalse(reviewed["grants_real_authority"])
        self.assertEqual(reviewed["independent_verification"], "NOT_ESTABLISHED")

    def test_claimed_verified_result_cannot_pass_report_audit(self):
        from eai.offline_journey import audit_offline_journey_report
        report = self.call()
        report["verified_real_world"] = True
        with self.assertRaises(ValueError):
            audit_offline_journey_report(report)

    def test_rehashed_status_reason_spoof_is_still_rejected(self):
        from eai.offline_journey import audit_offline_journey_report
        from eai.contracts import canonical_sha256
        for fake_status, fake_reasons in (
            ("PURE_ELIGIBLE_NOT_INTERPRETED", ["PLAN_POLICY_DENIED"]),
            ("POLICY_OR_RESOURCE_HELD", []),
        ):
            with self.subTest(status=fake_status):
                report = self.call(interpret=False)
                report["candidates"][0]["status"] = fake_status
                report["candidates"][0]["reason_codes"] = fake_reasons
                report["receipt_sha256"] = canonical_sha256({
                    k: v for k, v in report.items() if k != "receipt_sha256"
                })
                with self.assertRaisesRegex(ValueError, "reason/status"):
                    audit_offline_journey_report(report)

    def test_tampered_trace_checksum_rejected(self):
        from eai.offline_journey import audit_offline_journey_report
        report = self.call()
        report["candidate_count"] = 0
        with self.assertRaises(ValueError):
            audit_offline_journey_report(report)

    def test_declared_resource_tamper_denied_before_player(self):
        original = preview_architecture(self.problem_file, self.axnode_dir)
        changed = dict(original)
        changed["advisory_plans"] = [
            dict(option) for option in original["advisory_plans"]]
        changed["advisory_plans"][0]["declared_step_count"] = 0
        with patch("eai.offline_journey.preview_architecture",
                   return_value=changed):
            with self.assertRaisesRegex(ValueError, "resource requirements"):
                self.call(interpret=True)

    def test_missing_existing_store_not_created(self):
        missing = self.root / "unknown"
        with self.assertRaises(ValueError):
            preview_offline_journey(self.problem_file, missing)
        self.assertFalse(missing.exists())

    def test_journey_cli_policy_denial_still_returns_sanitized_preview(self):
        out, err = io.StringIO(), io.StringIO()
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=100 * 1024 * 1024):
            with redirect_stdout(out), redirect_stderr(err):
                code = main([
                    "journey-preview", "--problem-file", str(self.problem_file),
                    "--axnode-root", str(self.axnode_dir), "--interpret-pure",
                ])
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        report = json.loads(out.getvalue())
        self.assertEqual(report["candidate_count"], 2)
        self.assertNotIn("PRIVATE", out.getvalue())
        self.assertEqual(report["real_tool_invocations"], 0)

    def test_journey_cli_bad_source_is_sanitized(self):
        out, err = io.StringIO(), io.StringIO()
        missing = self.root / "nothing"
        with redirect_stdout(out), redirect_stderr(err):
            code = main([
                "journey-preview", "--problem-file", str(self.problem_file),
                "--axnode-root", str(missing),
            ])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn("PRIVATE", err.getvalue())
        self.assertNotIn(str(missing), err.getvalue())
