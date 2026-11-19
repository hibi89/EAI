"""P2 synthetic private workspace crash/restart and fail-closed schema checks.

Never opens an owner or customer database: each case owns a disposable tempfile.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from eai.desktop_state import DesktopState, WorkspaceLimits


class P2DesktopWorkspaceRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="eai-p2-workspace-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "workspace.sqlite3"
        self.state = DesktopState(self.root)

    def test_valid_restart_preserves_journal_and_limits(self):
        self.assertEqual(self.state.history(), [])
        self.assertFalse(self.path.exists())
        self.state.record("home", "command", "OK")
        self.state.set_limits(WorkspaceLimits(3, 20, 2))
        reopened = DesktopState(self.root)
        self.assertEqual(reopened.history()[0][1:], ("home", "command", "OK"))
        self.assertEqual(reopened.limits(), WorkspaceLimits(3, 20, 2))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))

    def test_foreign_existing_database_cannot_be_repurposed_or_repaired(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE customer_original(secret TEXT)")
            db.execute("INSERT INTO customer_original VALUES('not-for-EAI')")
        before = self.path.read_bytes()
        for operation in (self.state.history, self.state.limits,
                          lambda: self.state.record("home", "command", "OK")):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "preserve source"):
                    operation()
                self.assertEqual(self.path.read_bytes(), before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT secret FROM customer_original").fetchone(),
                             ("not-for-EAI",))
            self.assertFalse(db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='events'").fetchone())

    def test_dropped_schema_stays_dropped_and_fails_closed(self):
        self.state.record("home", "command", "OK")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE limits")
        before = self.path.read_bytes()
        for operation in (self.state.history, self.state.limits,
                          lambda: self.state.record("home", "command", "OK")):
            with self.assertRaisesRegex(ValueError, "preserve source"):
                operation()
            self.assertEqual(self.path.read_bytes(), before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='limits'").fetchone())

    def test_untrusted_trigger_is_not_invoked_on_append(self):
        self.state.record("home", "command", "OK")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TRIGGER unauthorized AFTER INSERT ON events "
                       "BEGIN DELETE FROM events; END")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "preserve source"):
            self.state.record("home", "command", "OK")
        self.assertEqual(before, self.path.read_bytes())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
