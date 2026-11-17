"""C24 digest-only explanation prevents prompt injection and fake verification."""
from dataclasses import replace
import json
import unittest

from eai.trace_renderer import (
    render_architect_explanation, render_player_explanation,
)


class TraceRendererTests(unittest.TestCase):
    @staticmethod
    def architect():
        return {
            "schema": "eai.architect.preview.v1",
            "problem_sha256": "a" * 64,
            "status": "CANDIDATES_UNVERIFIED", "truth_status": "UNVERIFIED",
            "execution": "NOT_EXECUTED", "model": "LOCAL_CPU_ONLY",
            "analysis": {"unknowns": ["PRIVATE password"],
                         "contradictions": [], "state": "UNVERIFIED"},
            "evidence_review_required": False,
            "advisory_plans": [{
                "alternative_id": "strategy.a",
                "status": "ADVISORY_UNVERIFIED_NOT_EXECUTED",
                "node_hashes": ["b" * 64],
                "plan_steps": [{"operator": "synthetic.noop.v1"}],
            }],
        }

    @staticmethod
    def player():
        return {
            "schema": "eai.player.preview.v1",
            "problem_sha256": "a" * 64, "plan_sha256": "b" * 64,
            "status": "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED",
            "real_world_verified": False,
            "automatic_learning": False, "active_promotion": False,
            "execution": "PURE_SYNTHETIC_NOOP_ONLY",
            "external_actions": 0, "original_writes": 0,
            "trace_sha256": "c" * 64, "interpreted_step_count": 1,
        }

    def test_architect_sanitizes_private_unknowns_and_sources(self):
        report = render_architect_explanation(self.architect())
        self.assertEqual(report["kind"], "ARCHITECT")
        self.assertEqual(report["uncertainty"]["unknown_count"], 1)
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertFalse(report["verified_real_world"])
        self.assertEqual(report["alternatives"][0]["source_sha256"],
                         ["b" * 64])

    def test_architect_false_verified_or_side_effectful_status_rejected(self):
        for patch in ({"truth_status": "VERIFIED"},
                      {"execution": "EXECUTED"},
                      {"model": "REMOTE"},
                      {"status": "ACTIVE"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                render_architect_explanation({**self.architect(), **patch})

    def test_architect_malicious_alternative_title_denied(self):
        raw = self.architect()
        raw["advisory_plans"][0]["alternative_id"] = "<script>PRIVATE</script>"
        with self.assertRaises(ValueError):
            render_architect_explanation(raw)

    def test_blocked_architect_has_no_advisory_plan(self):
        raw = self.architect()
        raw["status"] = "BLOCKED"
        with self.assertRaises(ValueError):
            render_architect_explanation(raw)
        raw["advisory_plans"] = []
        report = render_architect_explanation(raw)
        self.assertEqual(report["alternatives"], [])

    def test_player_receipt_explains_only_noop_trace(self):
        out = render_player_explanation(self.player())
        self.assertEqual(out["kind"], "PLAYER")
        self.assertEqual(out["trace_sha256"], "c" * 64)
        self.assertEqual(out["interpreted_steps"], 1)
        self.assertFalse(out["verified_real_world"])

    def test_player_real_action_or_training_claim_rejected(self):
        for patch in ({"real_world_verified": True},
                      {"original_writes": 1},
                      {"automatic_learning": True},
                      {"active_promotion": True},
                      {"status": "REAL_EXECUTION"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                render_player_explanation({**self.player(), **patch})

    def test_architect_terminal_text_is_private_data_free(self):
        from eai.trace_renderer import render_explanation_text
        summary = render_architect_explanation(self.architect())
        text = render_explanation_text(summary)
        self.assertIn("EAI ARCHITECT - UNVERIFIED", text)
        self.assertIn("UNKNOWN COUNT: 1", text)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("<script>", text)

    def test_player_terminal_text_rejects_forged_status(self):
        from eai.trace_renderer import render_explanation_text
        summary = render_player_explanation(self.player())
        self.assertIn("SYNTHETIC", render_explanation_text(summary))
        forged = dict(summary, status="REAL_EXECUTION")
        with self.assertRaises(ValueError):
            render_explanation_text(forged)

    def test_denied_player_explanation_keeps_zero_steps(self):
        raw = self.player()
        raw["status"], raw["execution"] = "HOLD_POLICY_DENIED", "DENIED"
        result = render_player_explanation(raw)
        self.assertEqual(result["interpreted_steps"], 0)
        self.assertIsNone(result["trace_sha256"])
