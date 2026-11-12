"""P36 acceptance harness regression; mocked tests are NEVER real Qwen proof."""
import json
import unittest
from unittest.mock import patch

from scripts.accept_local_qwen import accept_local_qwen, main


def reply(selected_id):
    return {"message": {"content": json.dumps(
        {"version": 1, "selected_id": selected_id})}}


class LocalQwenAcceptanceTests(unittest.TestCase):
    def test_ack_required_before_any_model_request(self):
        with patch("eai.goal_selector.fetch_json",
                   side_effect=AssertionError("must never call")):
            self.assertEqual("BLOCKED", accept_local_qwen()["status"])

    def test_remote_endpoint_forbidden_before_model(self):
        with patch("eai.goal_selector.fetch_json",
                   side_effect=AssertionError("must never call")):
            with self.assertRaisesRegex(ValueError, "loopback"):
                accept_local_qwen(url="https://remote.example:11434",
                                  acknowledge=True)

    def test_model_proposes_only_not_executes(self):
        with patch("eai.goal_selector.fetch_json",
                   return_value=reply("references")) as called, \
             patch("scripts.accept_local_qwen.run_approved",
                   side_effect=AssertionError("implicit execution")):
            report = accept_local_qwen(acknowledge=True)
        self.assertEqual("PASS", report["status"])
        self.assertEqual("SEPARATE_EXPLICIT_EXECUTION_REQUIRED",
                         report["approval"])
        self.assertEqual("references", report["selected_id"])
        self.assertNotIn("synthetic_cpu_receipt", report)
        called.assert_called_once()
        args = called.call_args
        self.assertEqual("http://127.0.0.1:11434/api/chat", args.args[0])
        prompt = args.kwargs["payload"]["messages"][1]["content"]
        self.assertNotIn("sku_a", prompt)
        self.assertNotIn("line_1", prompt)
        self.assertNotIn("customer", prompt.lower())

    def test_explicit_synthetic_approval_runs_separate_cpu_verification(self):
        with patch("eai.goal_selector.fetch_json",
                   return_value=reply("references")):
            report = accept_local_qwen(acknowledge=True,
                                       approve_synthetic_run=True)
        self.assertEqual("PASS", report["status"])
        self.assertEqual("PASS", report["synthetic_cpu_receipt"])
        self.assertIs(report["source_modified"], False)

    def test_wrong_model_decision_refused(self):
        with patch("eai.goal_selector.fetch_json",
                   return_value=reply("scheduler")):
            self.assertEqual("REJECTED",
                             accept_local_qwen(acknowledge=True)["status"])

    def test_unavailable_model_is_not_fake_success(self):
        with patch("eai.goal_selector.fetch_json",
                   side_effect=ConnectionError("offline")) as called:
            report = accept_local_qwen(acknowledge=True)
        self.assertEqual("BLOCKED", report["status"])
        called.assert_called_once()

    def test_unapproved_id_is_blocked(self):
        with patch("eai.goal_selector.fetch_json",
                   return_value=reply("unauthorized")):
            self.assertEqual("BLOCKED",
                             accept_local_qwen(acknowledge=True)["status"])

    def test_cli_without_local_ack_returns_three(self):
        with patch("eai.goal_selector.fetch_json",
                   side_effect=AssertionError("no model")):
            self.assertEqual(3, main([]))


if __name__ == "__main__":
    unittest.main()
