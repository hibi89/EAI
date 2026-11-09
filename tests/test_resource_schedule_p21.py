"""P21 independently provable resource-capacity scheduling; no work execution."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from eai.resource_schedule import (
    validate_resource_goal, execute_resource_goal, render_resource_plan
)
from eai.resource_schedule_receipt import verify_resource_receipt
from eai.goal_dispatch import execute_goal_document
from eai.goal_batch import execute_batch_document
from eai.goal_pipeline import execute_pipeline_document


def scenario():
    return {
        "version": 1, "kind": "resource_schedule",
        "goal": "Offline release plan", "horizon_hours": 8,
        "capacities": {"cpu": 1, "qa": 1},
        "tasks": [
            {"id": "ingest", "hours": 2, "requires": [],
             "resources": {"cpu": 1}},
            {"id": "prepare", "hours": 2, "requires": [],
             "resources": {"cpu": 1}},
            {"id": "verify", "hours": 1, "requires": ["ingest", "prepare"],
             "resources": {"qa": 1}}
        ]
    }


class ResourceScheduleP21Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.spec = self.root / "resource.json"
        self.write(scenario())

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, content):
        self.spec.write_text(json.dumps(content), encoding="utf-8")

    def run_goal(self, content=None):
        if content is not None:
            self.write(content)
        return execute_goal_document(self.spec)

    def test_optimal_schedule_shared_capacity(self):
        report = self.run_goal()
        self.assertEqual(report["status"], "DECIDED")
        self.assertEqual(report["route"], "task.resource_schedule.v1")
        self.assertEqual(report["verification"]["status"], "PASS")
        result = report["result"]
        self.assertEqual(result["makespan"], 5)
        self.assertEqual(result["minimum_lower_bound"], 4)
        self.assertEqual(result["slack_hours"], 3)
        self.assertEqual([x["id"] for x in result["schedule"]],
                         ["ingest", "prepare", "verify"])
        self.assertEqual(result["schedule"][-1]["start"], 4)
        self.assertIn("용량 제약", render_resource_plan(result))

    def test_increasing_cpu_capacity_enables_parallelism(self):
        data = scenario()
        data["capacities"]["cpu"] = 2
        report = self.run_goal(data)
        self.assertEqual(report["status"], "DECIDED")
        self.assertEqual(report["result"]["makespan"], 3)
        self.assertEqual(report["result"]["schedule"][-1]["start"], 2)

    def test_horizon_one_hour_too_short_is_unavailable(self):
        data = scenario()
        data["horizon_hours"] = 4
        report = self.run_goal(data)
        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertIsNone(report["result"]["makespan"])
        self.assertEqual(report["result"]["schedule"], [])
        self.assertEqual(report["verification"]["diagnostics"]["type"],
                         "RESOURCE_CAPACITY_OR_DEADLINE")

    def test_critical_path_longer_than_horizon(self):
        data = scenario()
        data["horizon_hours"] = 3
        self.assertEqual(self.run_goal(data)["status"], "UNAVAILABLE")

    def test_dependency_chain_longest_path(self):
        data = scenario()
        data["tasks"] = [
            {"id":"a","hours":2,"requires":[],"resources":{"cpu":1}},
            {"id":"b","hours":2,"requires":["a"],"resources":{"cpu":1}},
            {"id":"c","hours":2,"requires":["b"],"resources":{"cpu":1}}
        ]
        report = self.run_goal(data)
        self.assertEqual(report["status"], "DECIDED")
        self.assertEqual(report["result"]["makespan"], 6)
        self.assertEqual(report["result"]["minimum_lower_bound"], 6)

    def test_separate_resources_can_run_concurrently(self):
        data = scenario()
        data["tasks"] = [
            {"id":"a","hours":3,"requires":[],"resources":{"cpu":1}},
            {"id":"b","hours":2,"requires":[],"resources":{"qa":1}}
        ]
        self.assertEqual(self.run_goal(data)["result"]["makespan"], 3)

    def test_capacity_usage_does_not_allow_overbooking(self):
        data = scenario()
        data["capacities"]["cpu"] = 2
        data["tasks"][0]["resources"]["cpu"] = 2
        data["tasks"][1]["resources"]["cpu"] = 2
        self.assertEqual(self.run_goal(data)["result"]["makespan"], 5)

    def test_order_is_canonical_even_if_input_out_of_order(self):
        data = scenario()
        data["tasks"] = list(reversed(data["tasks"]))
        result = self.run_goal(data)["result"]
        self.assertEqual([item["id"] for item in result["tasks_contract"]],
                         ["ingest", "prepare", "verify"])

    def test_unknown_and_self_dependencies_rejected(self):
        for value in (["missing"], ["ingest"]):
            data = scenario()
            data["tasks"][0]["requires"] = value
            with self.subTest(dep=value), self.assertRaises(ValueError):
                self.run_goal(data)

    def test_cycles_rejected(self):
        data = scenario()
        data["tasks"][0]["requires"] = ["prepare"]
        data["tasks"][1]["requires"] = ["ingest"]
        with self.assertRaisesRegex(ValueError, "cyclic"):
            self.run_goal(data)

    def test_extra_actions_and_boolean_ints_denied(self):
        for change in ({"shell": "rm"}, {"horizon_hours": True},
                       {"capacities": {"cpu": True}},
                       {"tasks": []}, {"kind": "arbitrary"}, {"version": True}):
            data = scenario()
            data.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_goal(data)

    def test_task_demand_and_duration_must_be_valid(self):
        for task_change in (
            {"hours": 0}, {"hours": True}, {"hours": 9},
            {"resources": {"cpu": 2}}, {"resources": {"ram": 1}},
            {"resources": {}}, {"requires": ["prepare", "prepare"]},
            {"id": "bad task id"}, {"run": "shell"}
        ):
            data = scenario()
            data["tasks"][0].update(task_change)
            with self.subTest(task_change=task_change), self.assertRaises(ValueError):
                self.run_goal(data)

    def test_duplicate_ids_rejected(self):
        data = scenario()
        data["tasks"][1]["id"] = "ingest"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.run_goal(data)

    def test_receipt_independently_rejects_forged_nonoptimal_schedule(self):
        goal = validate_resource_goal(scenario())
        result = execute_resource_goal(goal)
        checks, diagnostic = verify_resource_receipt(goal, result)
        self.assertIn("global_optimality_proof", checks)
        self.assertEqual(diagnostic["type"], "NONE")
        for key, value in (
            ("status", "UNAVAILABLE"), ("makespan", 6), ("slack_hours", 4),
            ("capacities", {"cpu":2,"qa":1}), ("minimum_lower_bound", 1),
            ("schedule", [])
        ):
            corrupt = deepcopy(result)
            corrupt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_resource_receipt(goal, corrupt)

    def test_receipt_rejects_overlap_and_broken_predecessor(self):
        goal = validate_resource_goal(scenario())
        legit = execute_resource_goal(goal)
        forged = deepcopy(legit)
        forged["schedule"][1]["start"] = 0
        forged["schedule"][1]["end"] = 2
        with self.assertRaises(ValueError):
            verify_resource_receipt(goal, forged)
        forged = deepcopy(legit)
        forged["schedule"][-1]["start"] = 3
        forged["schedule"][-1]["end"] = 4
        with self.assertRaises(ValueError):
            verify_resource_receipt(goal, forged)

    def test_unavailable_receipt_independent_proof(self):
        data = scenario()
        data["horizon_hours"] = 4
        goal = validate_resource_goal(data)
        evidence = execute_resource_goal(goal)
        self.assertEqual(verify_resource_receipt(goal, evidence)[1]["type"],
                         "RESOURCE_CAPACITY_OR_DEADLINE")
        evidence["status"] = "DECIDED"
        with self.assertRaises(ValueError):
            verify_resource_receipt(goal, evidence)

    def test_no_user_files_changed(self):
        orig = self.spec.read_bytes()
        self.run_goal()
        self.assertEqual(self.spec.read_bytes(), orig)

    def test_cli_success_unavailable_and_invalid(self):
        root = Path(__file__).resolve().parent.parent
        def cli():
            return subprocess.run(
                [sys.executable, "-m", "eai", "solve-goal", str(self.spec), "--json"],
                cwd=root, capture_output=True, text=True, timeout=30
            )
        self.assertEqual(cli().returncode, 0)
        data = scenario()
        data["horizon_hours"] = 3
        self.write(data)
        self.assertEqual(cli().returncode, 3)
        data["execute"] = "anything"
        self.write(data)
        invalid = cli()
        self.assertEqual(invalid.returncode, 1)
        self.assertNotIn("Traceback", invalid.stderr)

    def test_batch_and_dependency_gate_hold(self):
        data = scenario()
        data["horizon_hours"] = 3
        self.write(data)
        follow = self.root / "other.json"
        follow.write_text(json.dumps({
            "version":1, "kind":"choose_options", "goal":"Choice",
            "criteria":[{"id":"cost","direction":"min","unit":"USD",
                         "weight":"1","score_min":"0","score_max":"100"}],
            "options":[{"id":"A","values":{"cost":"10"}},
                       {"id":"B","values":{"cost":"20"}}]
        }))
        def item(identifier, path, requires=None):
            row = {"id":identifier,"goal":path,
                   "sha256":hashlib.sha256((self.root / path).read_bytes()).hexdigest()}
            if requires is not None:
                row["requires"]=requires
            return row
        a, b = item("plan","resource.json"), item("next","other.json")
        manifest = self.root / "batch.json"
        manifest.write_text(json.dumps({
            "version":1,"kind":"goal_batch","continue_on_error":True,
            "items":[a,b]
        }))
        self.assertEqual(execute_batch_document(manifest)["status"], "REVIEW")
        pipe = self.root / "pipe.json"
        pipe.write_text(json.dumps({
            "version":1,"kind":"goal_pipeline","continue_on_error":True,
            "items":[dict(a,requires=[]),dict(b,requires=["plan"])]
        }))
        result = execute_pipeline_document(pipe)
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["verification"]["status"], "PASS")
        self.assertEqual(result["items"][1]["status"], "SKIPPED")


if __name__=="__main__":
    unittest.main()
