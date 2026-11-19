"""P2 synthetic private workspace crash/restart and fail-closed schema checks.

Never opens an owner or customer database: each case owns a disposable tempfile.
"""
from concurrent.futures import ThreadPoolExecutor
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

    def test_concurrent_first_open_serializes_new_schema_and_records(self):
        # Three first-start workers must not mistake another pending creator
        # for a damaged existing store. No user DB paths are touched.
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _: self.state.record("home", "command", "OK"), range(30)))
        self.assertEqual(len(DesktopState(self.root).history()), 30)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))

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


    def test_workspace_same_names_weak_schema_is_preserved(self):
        # A foreign owner file with matching column names is not our journal.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE events("
                       "id TEXT, stamp TEXT, page TEXT, op TEXT, status TEXT)")
            db.execute("CREATE TABLE limits("
                       "id TEXT, steps TEXT, seconds TEXT, expansions TEXT)")
            db.execute("INSERT INTO events VALUES('owner','original','home','command','OK')")
        before = self.path.read_bytes()
        for operation in (
            self.state.history,
            self.state.limits,
            lambda: self.state.record("home", "command", "OK"),
            lambda: self.state.set_limits(WorkspaceLimits()),
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "preserve source"):
                    operation()
                self.assertEqual(self.path.read_bytes(), before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT id,stamp FROM events").fetchone(),
                             ("owner", "original"))

    def test_workspace_extra_index_is_not_used_for_owner_writes(self):
        self.state.record("home", "command", "OK")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE INDEX extra_owner_index ON events(op)")
        before = self.path.read_bytes()
        for operation in (
            self.state.history,
            lambda: self.state.record("home", "command", "OK"),
            lambda: self.state.set_limits(WorkspaceLimits(2, 5, 1)),
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "preserve source"):
                    operation()
                self.assertEqual(self.path.read_bytes(), before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone(), (1,))

    def test_existing_zero_byte_workspace_is_preserved(self):
        self.path.write_bytes(b"")
        for operation in (
            self.state.history,
            lambda: self.state.record("home", "command", "OK"),
            lambda: self.state.set_limits(WorkspaceLimits()),
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "preserve source"):
                    operation()
                self.assertEqual(self.path.read_bytes(), b"")

    @staticmethod
    def session_draft():
        from eai.desktop_bridge import DesktopBridge
        return DesktopBridge.make_problem_draft(
            "합성 로컬 세션을 안전하게 저장하고 다시 검토한다")

    def test_existing_zero_byte_session_file_is_preserved_not_reused(self):
        session_path = self.root / "review_sessions.sqlite3"
        session_path.write_bytes(b"")
        for operation in (
            self.state.load_session,
            lambda: self.state.save_session(
                self.session_draft(), owner_approved=True),
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "preserve source"):
                    operation()
                self.assertEqual(session_path.read_bytes(), b"")
                self.assertEqual(session_path.stat().st_size, 0)

    def test_existing_foreign_or_weak_session_schema_never_repaired(self):
        session_path = self.root / "review_sessions.sqlite3"
        with closing(sqlite3.connect(session_path)) as db, db:
            db.execute("CREATE TABLE sessions("
                       "id INTEGER, stamp INTEGER, sha256 TEXT, payload BLOB)")
            db.execute("PRAGMA user_version=1")
            db.execute("INSERT INTO sessions VALUES(1,1,'owner','original')")
        before = session_path.read_bytes()
        for operation in (
            self.state.load_session,
            lambda: self.state.save_session(
                self.session_draft(), owner_approved=True),
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "preserve source"):
                    operation()
                self.assertEqual(session_path.read_bytes(), before)
        with closing(sqlite3.connect(session_path)) as db:
            self.assertEqual(db.execute(
                "SELECT payload FROM sessions WHERE id=1").fetchone()[0],
                "original")

    def test_extra_session_schema_objects_block_save_without_mutating_history(self):
        for ddl in (
            "CREATE VIEW forged_session AS SELECT payload FROM sessions",
            "CREATE TRIGGER forged_session AFTER INSERT ON sessions "
            "BEGIN DELETE FROM sessions; END",
            "CREATE INDEX forbidden_session_idx ON sessions(stamp)",
        ):
            with self.subTest(ddl=ddl), TemporaryDirectory() as folder:
                root = Path(folder)
                state = DesktopState(root)
                draft = self.session_draft()
                first = state.save_session(draft, owner_approved=True)
                self.assertTrue(first["saved"])
                db_path = root / "review_sessions.sqlite3"
                with closing(sqlite3.connect(db_path)) as db, db:
                    db.execute(ddl)
                before = db_path.read_bytes()
                with self.assertRaisesRegex(ValueError, "preserve source"):
                    state.save_session(draft, owner_approved=True)
                self.assertEqual(db_path.read_bytes(), before)
                with self.assertRaisesRegex(ValueError, "preserve source"):
                    state.load_session()
                self.assertEqual(db_path.read_bytes(), before)
                with closing(sqlite3.connect(db_path)) as db:
                    self.assertEqual(db.execute(
                        "SELECT COUNT(*) FROM sessions").fetchone(), (1,))

    def test_concurrent_new_review_sessions_are_private_and_resume_review_only(self):
        draft = self.session_draft()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.state.save_session(
                draft, owner_approved=True), range(12)))
        self.assertEqual(len(results), 12)
        self.assertTrue(all(r["status"] == "SESSION_SAVED_REVIEW_ONLY"
                            for r in results))
        self.assertEqual(len({r["session_id"] for r in results}), 12)
        resumed = DesktopState(self.root).load_session()
        self.assertEqual(resumed["status"], "SESSION_RESTORED_REVIEW_REQUIRED")
        self.assertEqual(resumed["draft"], draft)
        self.assertIs(resumed["can_execute"], False)
        with closing(sqlite3.connect(self.root / "review_sessions.sqlite3")) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM sessions").fetchone(), (12,))
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))

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
