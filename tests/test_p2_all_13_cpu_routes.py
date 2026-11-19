"""P2-03 same-SHA 13 real CPU goal routes with disposable synthetic inputs.

Tests the actual dispatcher and independent receipt guards across all registered
local CPU domains. Never consumes owner/customer files or runs P26/Player.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from eai.goal_dispatch import ROUTED_KINDS, execute_goal_document


class AllThirteenOfflineRoutesTests(unittest.TestCase):
    # Exact real examples, not in-memory mock or assumed domain names.
    SAMPLE_GOALS = {
        "choose_options": "sample_hardware_decision.json",
        "csv_audit": "sample_csv_audit_goal.json",
        "plan_tasks": "sample_task_portfolio_goal.json",
        "schedule_tasks": "sample_task_schedule_goal.json",
        "csv_quality": "sample_csv_quality_goal.json",
        "csv_schema_drift": "sample_csv_schema_drift_goal.json",
        "csv_relationships": "sample_csv_relationships_goal.json",
        "local_evidence_search": "sample_local_evidence_goal.json",
        "resource_schedule": "sample_resource_schedule_goal.json",
        "csv_robust_outliers": "sample_robust_outliers_goal.json",
        "csv_key_coverage": "sample_key_coverage_goal.json",
    }
    EXTRA_GOALS = {
        "sqlite_table_audit": {
            "version": 1, "kind": "sqlite_table_audit",
            "goal": "Disposable invoice quality", "source": "synthetic.sqlite3",
            "table": "invoices", "required": ["id", "amount"],
            "unique_by": ["id"],
        },
        "csv_distribution_shift": {
            "version": 1, "kind": "csv_distribution_shift",
            "goal": "Disposable cohort parity",
            "baseline": "before.csv", "current": "after.csv",
            "encoding": "utf-8-sig", "columns": ["amount"],
            "min_rows": 5, "threshold": "2",
        },
    }
    EXPECTED_ROUTES = {
        "choose_options": "decision.select.v1",
        "csv_audit": "csv.audit_plan.v1",
        "plan_tasks": "task.portfolio.v1",
        "schedule_tasks": "task.critical_path.v1",
        "csv_quality": "csv.quality_gate.v1",
        "csv_schema_drift": "csv.schema_drift.v1",
        "sqlite_table_audit": "sqlite.table_audit.v1",
        "csv_relationships": "csv.relationships.v1",
        "local_evidence_search": "local.evidence_search.v1",
        "resource_schedule": "task.resource_schedule.v1",
        "csv_robust_outliers": "csv.robust_outliers.v1",
        "csv_distribution_shift": "csv.distribution_shift.v1",
        "csv_key_coverage": "csv.key_coverage.v1",
    }

    def setUp(self):
        tmp = TemporaryDirectory(prefix="eai-p2-13-goals-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        sample_root = Path(__file__).resolve().parent.parent / "examples"
        for name in (*self.SAMPLE_GOALS.values(),
                     *[p.name for p in sample_root.iterdir()
                       if p.suffix in {".csv", ".md", ".txt"}]):
            shutil.copy2(sample_root / name, self.root / name)
        with closing(sqlite3.connect(self.root / "synthetic.sqlite3")) as db, db:
            db.execute("CREATE TABLE invoices (id TEXT, amount INTEGER)")
            db.executemany("INSERT INTO invoices VALUES(?,?)",
                           (("A", 10), ("B", 20), ("B", 30)))
        for name in ("before.csv", "after.csv"):
            (self.root / name).write_text(
                "amount\n" + "\n".join(str(n) for n in range(1, 12)) + "\n",
                encoding="utf-8")
        for kind, payload in self.EXTRA_GOALS.items():
            (self.root / (kind + ".json")).write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_every_registered_cpu_route_runs_real_solver_and_receipt_guard(self):
        self.assertEqual(len(ROUTED_KINDS), 13)
        self.assertEqual(set(self.SAMPLE_GOALS) | set(self.EXTRA_GOALS), ROUTED_KINDS)
        self.assertEqual(set(self.EXPECTED_ROUTES), ROUTED_KINDS)
        baseline = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.iterdir() if p.is_file()}
        seen = set()
        with patch.object(socket.socket, "connect",
                          side_effect=AssertionError("network forbidden")), \
             patch("eai.approved_run.run_approved",
                   side_effect=AssertionError("P26 owner GO is not present")):
            for kind in sorted(ROUTED_KINDS):
                with self.subTest(domain=kind):
                    goal_name = self.SAMPLE_GOALS.get(kind, kind + ".json")
                    doc = self.root / goal_name
                    assert doc.is_file(), goal_name
                    goal_bytes = doc.read_bytes()
                    report = execute_goal_document(doc)
                    self.assertEqual(report["kind"], kind)
                    self.assertEqual(report["route"], self.EXPECTED_ROUTES[kind])
                    self.assertEqual(report["input"]["sha256"],
                                     hashlib.sha256(goal_bytes).hexdigest())
                    self.assertEqual(report["verification"]["status"], "PASS")
                    self.assertEqual(report["dispatcher_version"],
                                     "eai.goal.dispatch.v1")
                    self.assertEqual(report["steps"][0]["status"], "PASS")
                    self.assertEqual(report["steps"][-1]["status"], "PASS")
                    self.assertEqual(report["result"]["status"], report["status"])
                    self.assertEqual(len(report["steps"]), 3)
                    seen.add(kind)
        self.assertEqual(seen, ROUTED_KINDS)
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(after, baseline, "CPU route changed input or created a file")

    def test_invalid_synthetic_sqlite_and_goal_kind_fail_before_any_execution(self):
        goal = self.root / "sqlite_table_audit.json"
        before = (self.root / "synthetic.sqlite3").read_bytes()
        raw = json.loads(goal.read_text(encoding="utf-8"))
        raw["sql"] = "DELETE FROM invoices"
        goal.write_text(json.dumps(raw), encoding="utf-8")
        with patch("eai.goal_dispatch.execute_sqlite_goal",
                   side_effect=AssertionError("untrusted goal executed")):
            with self.assertRaises(ValueError):
                execute_goal_document(goal)
        self.assertEqual(before, (self.root / "synthetic.sqlite3").read_bytes())
        goal.write_text('{"version":1,"kind":"shell.execute"}',encoding="utf-8")
        with patch("eai.goal_dispatch.execute_choice_goal",
                   side_effect=AssertionError("unsupported goal executed")):
            with self.assertRaises(ValueError):
                execute_goal_document(goal)


if __name__ == "__main__":
    unittest.main()
