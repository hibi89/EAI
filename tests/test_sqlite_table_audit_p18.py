"""P18 SQLite CPU audit: private local DB, independent evidence and gating."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.sqlite_table_audit import (
    MAX_DB_BYTES, execute_sqlite_goal, render_sqlite, validate_sqlite_goal
)
from eai.sqlite_receipt import verify_sqlite_receipt
from eai.goal_dispatch import execute_goal_document
from eai.goal_batch import execute_batch_document
from eai.goal_pipeline import execute_pipeline_document


def audit_spec():
    return {
        "version": 1, "kind": "sqlite_table_audit", "goal": "Invoice check",
        "source": "synthetic.sqlite3", "table": "invoices",
        "required": ["id", "amount"], "unique_by": ["id"]
    }


def choice_spec():
    return {
        "version": 1, "kind": "choose_options", "goal": "Choose CPU",
        "criteria": [{
            "id": "cost", "direction": "min", "unit": "USD",
            "weight": "1", "score_min": "0", "score_max": "100"
        }],
        "options": [
            {"id": "A", "values": {"cost": "1"}},
            {"id": "B", "values": {"cost": "2"}}
        ]
    }


class SqliteTableAuditP18Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "synthetic.sqlite3"
        self.goal = self.root / "audit.json"
        self.write(audit_spec())
        with sqlite3.connect(self.db) as con:
            con.execute("CREATE TABLE invoices (id TEXT, amount INTEGER, note TEXT)")
            con.executemany(
                "INSERT INTO invoices (id, amount, note) VALUES (?, ?, ?)",
                [
                    ("A", 10, "CUSTOMER_PRIVATE_7378"),
                    ("B", 20, "regular"),
                    ("B", 30, "regular"),
                    ("C", None, "missing"),
                    ("", 40, "blank id")
                ]
            )

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.goal.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def run_goal(self, data=None):
        if data is not None:
            self.write(data)
        return execute_goal_document(self.goal)

    def change_rows(self, rows):
        with sqlite3.connect(self.db) as con:
            con.execute("DELETE FROM invoices")
            con.executemany(
                "INSERT INTO invoices VALUES (?, ?, ?)", rows
            )

    def test_conflict_counts_and_verifier(self):
        report = self.run_goal()
        self.assertEqual(report["status"], "CONFLICT")
        self.assertEqual(report["route"], "sqlite.table_audit.v1")
        self.assertEqual(report["verification"]["status"], "PASS")
        self.assertEqual(
            report["verification"]["diagnostics"]["type"], "SQLITE_INTEGRITY_REVIEW"
        )
        result = report["result"]
        self.assertEqual(result["rows"], 5)
        self.assertEqual(result["counts"], {
            "MISSING_REQUIRED": 2, "DUPLICATE_KEY": 1
        })
        self.assertEqual(result["affected_records"], 3)
        self.assertEqual(len(result["samples"]), 3)
        self.assertIn("SQLite", render_sqlite(result))

    def test_clean_source_is_agree(self):
        self.change_rows([("A", 10, "a"), ("B", 20, "b")])
        self.assertEqual(self.run_goal()["status"], "AGREE")
        self.assertEqual(self.run_goal()["result"]["samples"], [])

    def test_empty_is_unavailable(self):
        self.change_rows([])
        report = self.run_goal()
        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertEqual(
            report["verification"]["diagnostics"]["type"], "SQLITE_EMPTY"
        )

    def test_zero_and_integer_keys_are_not_blank(self):
        self.change_rows([(0, 0, "n"), (1, 0, "n")])
        self.assertEqual(self.run_goal()["status"], "AGREE")

    def test_composite_keys_not_concatenated(self):
        data = audit_spec()
        data["required"] = ["id", "note"]
        data["unique_by"] = ["id", "note"]
        self.change_rows([("A", 1, "BC"), ("AB", 2, "C"), ("A", 3, "BC")])
        self.assertEqual(self.run_goal(data)["result"]["counts"]["DUPLICATE_KEY"], 1)

    def test_real_values_never_leave_receipt(self):
        serialized = json.dumps(self.run_goal(), ensure_ascii=False)
        self.assertNotIn("CUSTOMER_PRIVATE_7378", serialized)
        self.assertNotIn("regular", serialized)
        self.assertNotIn("blank id", serialized)
        self.assertIn("MISSING_REQUIRED", serialized)

    def test_database_and_goal_bytes_unchanged(self):
        original_db = self.db.read_bytes()
        original_goal = self.goal.read_bytes()
        self.run_goal()
        self.assertEqual(self.db.read_bytes(), original_db)
        self.assertEqual(self.goal.read_bytes(), original_goal)
        for suffix in ("-wal", "-journal", "-shm"):
            self.assertFalse(self.db.with_name(self.db.name + suffix).exists())

    def test_goal_contract_denies_unknown_keys_and_sql(self):
        for addition in ({"sql": "DROP TABLE invoices"}, {"write": True},
                         {"version": True}, {"kind": "shell"}):
            payload = audit_spec()
            payload.update(addition)
            with self.subTest(addition=addition), self.assertRaises(ValueError):
                self.run_goal(payload)

    def test_bad_names_and_unknown_columns_denied(self):
        for table in ("invoices; DROP TABLE users", "sqlite_master", "missing", "a b"):
            data = audit_spec()
            data["table"] = table
            with self.subTest(table=table), self.assertRaises(ValueError):
                self.run_goal(data)
        for name in ("does_not_exist", "note; --"):
            data = audit_spec()
            data["required"] = ["id", name]
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.run_goal(data)

    def test_rejects_unbounded_or_duplicate_rules(self):
        for required, key in [
            (["id", "ID"], ["id"]),
            (["amount"], ["id"]),
            (["id"] * 9, ["id"])
        ]:
            data = audit_spec()
            data["required"], data["unique_by"] = required, key
            with self.assertRaises(ValueError):
                self.run_goal(data)

    def test_absolute_parent_and_windows_style_paths_denied(self):
        for path in ("../secret.sqlite3", "/tmp/foo.sqlite", "C:\\secret.sqlite3",
                     ".\\synthetic.sqlite3"):
            data = audit_spec()
            data["source"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_goal(data)

    def test_symlink_outside_goal_folder_denied(self):
        with tempfile.TemporaryDirectory() as outside:
            link = self.root / "outside.sqlite3"
            try:
                link.symlink_to(self.db)
                # A symlink pointing at the current in-folder DB is permitted.
                data = audit_spec()
                data["source"] = link.name
                self.assertEqual(self.run_goal(data)["status"], "CONFLICT")
                link.unlink()
                remote = Path(outside) / "secret.sqlite3"
                remote.write_bytes(self.db.read_bytes())
                link.symlink_to(remote)
            except (OSError, NotImplementedError):
                self.skipTest("OS does not allow creating symlinks")
            with self.assertRaises(ValueError):
                self.run_goal(data)

    def test_refuses_views_and_generated_columns(self):
        with sqlite3.connect(self.db) as con:
            con.execute("CREATE VIEW copy_invoice AS SELECT * FROM invoices")
            con.execute(
                "CREATE TABLE generated (id TEXT, derived INTEGER "
                "GENERATED ALWAYS AS (length(id)) VIRTUAL)"
            )
        for table in ("copy_invoice", "generated"):
            data = audit_spec()
            data["table"] = table
            data["required"] = ["id"]
            data["unique_by"] = ["id"]
            with self.subTest(table=table), self.assertRaises(ValueError):
                self.run_goal(data)

    def test_rejects_active_wal_and_journal_sidecar(self):
        wal = self.db.with_name(self.db.name + "-wal")
        wal.write_bytes(b"synthetic sidecar")
        with self.assertRaisesRegex(ValueError, "WAL"):
            self.run_goal()
        wal.unlink()
        self.assertEqual(self.run_goal()["status"], "CONFLICT")

    def test_rejects_non_sqlite_bytes_and_large_database(self):
        self.db.write_bytes(b"not a database")
        with self.assertRaises(ValueError):
            self.run_goal()
        self.db.write_bytes(b"SQLite format 3\x00")
        with self.db.open("ab") as file:
            file.truncate(MAX_DB_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "16MiB"):
            self.run_goal()

    def test_row_limit_fail_closed(self):
        self.change_rows([(str(i), i, "x") for i in range(20001)])
        with self.assertRaisesRegex(ValueError, "20000"):
            self.run_goal()

    def test_forged_receipt_rejected(self):
        goal = validate_sqlite_goal(audit_spec(), self.goal)
        legit = execute_sqlite_goal(goal)
        self.assertEqual(verify_sqlite_receipt(goal, legit)[1]["type"],
                         "SQLITE_INTEGRITY_REVIEW")
        for field, fake in (
            ("status", "AGREE"), ("rows", 0), ("sha256", "0" * 64),
            ("samples", []), ("affected_records", 1)
        ):
            tampered = deepcopy(legit)
            tampered[field] = fake
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_sqlite_receipt(goal, tampered)

    def test_detects_database_changed_during_primary_scan(self):
        from eai.sqlite_table_audit import _connect_and_read
        def changing(goal):
            result = _connect_and_read(goal)
            with sqlite3.connect(self.db) as con:
                con.execute("INSERT INTO invoices VALUES ('new', 1, 'after')")
            return result
        with patch("eai.sqlite_table_audit._connect_and_read", side_effect=changing):
            with self.assertRaisesRegex(ValueError, "changed during scan"):
                self.run_goal()

    def test_cli_conflict_agree_empty_and_failure_exit_codes(self):
        root = Path(__file__).resolve().parent.parent
        def run():
            return subprocess.run(
                [sys.executable, "-m", "eai", "solve-goal", str(self.goal), "--json"],
                cwd=root, capture_output=True, text=True, timeout=30
            )
        conflict = run()
        self.assertEqual(conflict.returncode, 2, conflict.stderr)
        self.assertEqual(json.loads(conflict.stdout)["status"], "CONFLICT")
        self.change_rows([("Z", 1, "x")])
        self.assertEqual(run().returncode, 0)
        self.change_rows([])
        self.assertEqual(run().returncode, 3)
        data = audit_spec()
        data["sql"] = "SELECT secret FROM users"
        self.write(data)
        error = run()
        self.assertEqual(error.returncode, 1)
        self.assertIn("EAI GOAL ERROR", error.stderr)
        self.assertNotIn("Traceback", error.stderr)

    def test_verified_batch_and_dependency_hold(self):
        choice = self.root / "choice.json"
        choice.write_text(json.dumps(choice_spec()))
        def entry(identifier, name, requires=None):
            target = self.root / name
            value = {
                "id": identifier, "goal": name,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest()
            }
            if requires is not None:
                value["requires"] = requires
            return value
        first = entry("check", "audit.json")
        second = entry("choice", "choice.json")
        batch = self.root / "batch.json"
        batch.write_text(json.dumps({
            "version": 1, "kind": "goal_batch",
            "continue_on_error": True, "items": [first, second]
        }))
        outcome = execute_batch_document(batch)
        self.assertEqual(outcome["status"], "REVIEW")
        self.assertEqual(outcome["verification"]["status"], "PASS")
        pipeline = self.root / "pipe.json"
        pipeline.write_text(json.dumps({
            "version": 1, "kind": "goal_pipeline",
            "continue_on_error": True,
            "items": [dict(first, requires=[]),
                      dict(second, requires=["check"])]
        }))
        report = execute_pipeline_document(pipeline)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["verification"]["status"], "PASS")
        self.assertEqual(
            next(x for x in report["items"] if x["id"] == "choice")["blocked_by"],
            ["check"]
        )


if __name__ == "__main__":
    unittest.main()
