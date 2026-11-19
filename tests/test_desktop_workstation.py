"""Real CPU, disposable SQLite and native Tk. Only file/confirmation dialogs are scripted."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from eai.contracts import canonical_sha256
from eai.desktop_app import EAIDesktopApp
from eai.desktop_bridge import DesktopBridge
from eai.desktop_example import PracticeWorkspace
from eai.desktop_presentation import PAGES
from eai.desktop_state import WorkspaceLimits
from eai.local_files import local_path


class WorkstationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "한글 자료"
        self.bridge = DesktopBridge(self.root)
        self.offline = patch.object(
            socket.socket, "connect", side_effect=AssertionError("unexpected socket"))
        self.offline.start()
        self.addCleanup(self.offline.stop)

    def fixture(self):
        w = PracticeWorkspace()
        self.addCleanup(w.close)
        return w

    def test_command_cli_parity_no_raw_turns_and_confirmed_memo_reopens(self):
        from eai.runner import EAIRunner
        from eai.storage import Store
        question = "계산: 12 * (3 + 4)"
        answer = self.bridge.ask(question)
        with closing(Store(self.root / "cli.sqlite")) as store:
            self.assertEqual(answer["text"], EAIRunner(store).ask(question).text)
            self.assertEqual(len(store.recent_turns()), 2)
        self.assertEqual(self.bridge.ask("기억해: 연습 메모", consent_to_note=1)["status"],
                         "HOLD_EXPLICIT_NOTE_APPROVAL")
        self.bridge.ask("기억해: 연습 메모", consent_to_note=True)
        self.assertIn("연습 메모", DesktopBridge(self.root).ask("메모목록")["text"])
        with closing(sqlite3.connect(self.root / "desktop_history.sqlite3")) as db:
            self.assertEqual(db.execute("select count(*) from turns").fetchone()[0], 0)
        self.assertEqual(self.bridge.ask("계산: 1 / 0")["status"], "ERROR")

    def test_two_designs_read_only_catalog_and_hash_checked_lineage(self):
        w = self.fixture()
        def files():
            return {p.relative_to(w.library): hashlib.sha256(p.read_bytes()).digest()
                    for p in w.library.rglob("*") if p.is_file()}
        before = files()
        report = self.bridge.architect(w.problem, w.library)
        self.assertEqual(len(report["alternatives"]), 2)
        self.assertEqual(self.bridge.architect(w.problem, w.library, cancelled=lambda: True)["status"], "CANCELLED")
        hits = self.bridge.axnode_catalog(w.library, query="revision", status="CANDIDATE")
        self.assertEqual(hits["shown"], 1)
        detail = self.bridge.node_detail(w.library, hits["nodes"][0]["sha256"])
        self.assertEqual(self.bridge.node_detail(w.library, detail["parents"][0])["node_id"], "practice.review")
        self.assertEqual(detail["source"], "bundled_example")
        self.assertEqual(self.bridge.axnode_catalog(w.library, status="DRAFT")["shown"], 0)
        self.assertEqual(files(), before)

    def test_live_wal_reader_sees_commits_without_touching_source(self):
        from eai.axnode_store import AXNodeStore
        w = self.fixture()
        with AXNodeStore(w.library) as writer:
            node = writer.get(writer.hashes()[0]).as_dict()
            node["id"] = "practice.extra"
            writer.import_node(json.dumps(node))
            wal = w.library / "axnodes.sqlite-wal"
            before = hashlib.sha256(wal.read_bytes()).digest()
            self.assertEqual(self.bridge.axnode_catalog(w.library)["shown"], 4)
            self.assertEqual(hashlib.sha256(wal.read_bytes()).digest(), before)

    def test_plan_revalidation_cancel_and_approval(self):
        w = self.fixture()
        review = self.bridge.inspect_plan(w.problem, w.plan)
        digests = review["problem_sha256"], review["plan_sha256"]
        args = dict(acknowledged_pure_only=True, reviewed_digests=digests)
        out = self.bridge.player(w.problem, w.plan, cancel_before_step="review", **args)
        self.assertEqual((out["interpreted_steps"], out["external_actions"]), (1, 0))
        self.assertEqual(out["replay"], "PURE_TRACE_REPLAY_MATCH_UNVERIFIED")
        raw = json.loads(w.plan.read_bytes())
        raw["steps"][0]["id"] = "changed"
        raw["steps"][1]["requires"] = ["changed"]
        w.plan.write_text(json.dumps(raw), encoding="utf-8")
        self.assertEqual(self.bridge.player(w.problem, w.plan, **args)["status"], "HOLD_PLAN_CHANGED")
        raw["steps"][0]["operator"] = "csv.reconcile.v1"
        w.plan.write_text(json.dumps(raw), encoding="utf-8")
        self.assertEqual(self.bridge.inspect_plan(w.problem, w.plan)["status"], "HOLD_POLICY_DENIED")

    def test_verifier_distinguishes_digest_failure_and_invalid_contract(self):
        w = self.fixture()
        result = self.bridge.verify_journey(w.receipt)
        self.assertEqual(result["receipt_sha256"], result["calculated_sha256"])
        self.assertEqual(result["independent_verification"], "NOT_ESTABLISHED")
        data = json.loads(w.receipt.read_bytes())
        data["unknown_count"] += 1
        w.receipt.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.bridge.verify_journey(w.receipt)["status"], "RECEIPT_DIGEST_MISMATCH")
        data["verified_real_world"] = True
        data.pop("receipt_sha256")
        data["receipt_sha256"] = canonical_sha256(data)
        w.receipt.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.bridge.verify_journey(w.receipt)["status"], "RECEIPT_CONTRACT_REJECTED")

    def test_journal_retention_settings_concurrency_and_exclusive_draft(self):
        state = self.bridge.state
        with ThreadPoolExecutor(3) as pool:
            list(pool.map(lambda _: state.record("home", "command", "OK"), range(108)))
        state.set_limits(WorkspaceLimits(3, 20, 2))
        self.assertEqual(DesktopBridge(self.root).state.limits(), WorkspaceLimits(3, 20, 2))
        self.assertEqual(len(state.history()), 100)
        raw = self.bridge.make_problem_draft("새 초안")
        saved = self.bridge.save_new_draft(raw)
        with self.assertRaises(FileExistsError):
            self.bridge.save_new_draft(raw)
        self.assertEqual(self.bridge.load_draft(saved), raw)
        with self.assertRaises(ValueError):
            local_path(self.root / ".." / "unused.json")
        with closing(sqlite3.connect(self.root / "workspace.sqlite3")) as db:
            self.assertEqual(db.execute("pragma integrity_check").fetchone(), ("ok",))

    def test_bounded_catalog_uses_matching_rows_for_truncation(self):
        w = self.fixture()
        with closing(sqlite3.connect(w.library / "axnodes.sqlite")) as db, db:
            db.executemany("INSERT INTO nodes VALUES(?,?,?,?,?,?,?)",
                [(f"{i:064x}", f"test.{i:03}", 1, "DRAFT", "strategy", "text", "bulk") for i in range(240)])
        self.assertEqual(self.bridge.axnode_catalog(w.library, query="bulk")["shown"], 200)
        self.assertTrue(self.bridge.axnode_catalog(w.library, query="bulk")["truncated"])
        self.assertFalse(self.bridge.axnode_catalog(w.library, query="baseline")["truncated"])


class NativeWorkstationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bridge = DesktopBridge(Path(self.temp.name) / "한글")
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("native Tk display unavailable")
        self.root.geometry("1100x680")
        self.app = EAIDesktopApp(self.root, self.bridge)
        self.addCleanup(self.cleanup_window)
        self.wait()

    def cleanup_window(self):
        if self.app is not None:
            self.wait()
            self.app.close()

    def wait(self):
        start = time.monotonic()
        while self.app.busy and time.monotonic()-start < 12:
            self.root.update()
            time.sleep(.005)
        self.assertFalse(self.app.busy)
        self.root.update()

    def test_seven_pages_composer_resize_and_keyboard(self):
        layouts = (
            ("1920x1080", 96/72), ("1366x768", 96/72), ("1366x768", 120/72),
            ("1340x694", 96/72), ("1100x590", 120/72), ("760x475", 120/72),
        )
        for geometry, scaling in layouts:
            self.root.tk.call("tk", "scaling", scaling)
            self.root.geometry(geometry)
            for page in PAGES:
                self.app.nav[page][2].invoke()
                self.root.update()
                self.assertEqual(self.app.page, page)
                for w in (self.app.command, self.app.send, self.app.nav["settings"][2]):
                    self.assertTrue(w.winfo_viewable())
                    self.assertLessEqual(w.winfo_rooty()+w.winfo_height(),
                                         self.root.winfo_rooty()+self.root.winfo_height()+1)
        self.app.fill_command("계산: 3 * 7")
        self.app.command.focus_force()
        self.root.update()
        self.app.command.event_generate("<Shift-Return>")
        self.assertTrue(self.app.command.get("1.0", "end-1c").endswith("\n"))
        self.app.command.event_generate("<Return>")
        self.wait()
        self.assertIn("21", self.app.results["home"][1]["text"])
        self.app.fill_command("지원 밖 임의 요청")
        self.app.send.invoke()
        self.wait()
        self.assertEqual(self.app.results["home"][1]["status"], "HOLD_UNSUPPORTED_REQUEST")
        self.app.newdraft.invoke()
        self.assertEqual(self.app.draft["goal"], "지원 밖 임의 요청")

    def test_workspace_journey_failure_and_restart(self):
        a = self.app
        a.practice()
        self.wait()
        for page, op, fn, status in (
            ("architect", "design", a.design, "CANDIDATES_UNVERIFIED"),
            ("atlas", "catalog", a.catalog, "LOCAL_CATALOG_UNVERIFIED"),
            ("player", "plan", a.inspect_plan, "PURE_SYNTHETIC_PREVIEW_ONLY"),
            ("verifier", "verify", a.verify, "LOCAL_JOURNEY_DIGEST_INTEGRITY_UNVERIFIED")):
            a.select(page)
            fn()
            self.wait()
            self.assertEqual(a.results[page][1]["status"], status)
        a.select("atlas")
        a.inspect_node(a.catalog_data["nodes"][0]["sha256"])
        self.wait()
        self.assertEqual(a.node_data["status"], "NODE_DIGEST_MATCH")
        a.select("player")
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            a.simulate()
            self.wait()
        self.assertEqual(a.results["player"][1]["interpreted_steps"], 2)
        a.select("architect")
        a.save()
        self.wait()
        saved = a.problem
        self.assertEqual(a.bridge.load_draft(saved), a.draft)
        a.select("settings")
        a.limit_vars[0].set("4")
        a.set_limits()
        self.wait()
        with patch("eai.desktop_app.filedialog.askopenfilename", return_value=""):
            a.open_problem("architect")
        self.assertEqual(a.problem, saved)
        bad = Path(self.temp.name) / "오류.json"
        bad.write_bytes(b"{")
        with patch("eai.desktop_app.filedialog.askopenfilename", return_value=str(bad)):
            a.open_problem("architect")
        self.wait()
        self.assertEqual(a.problem, saved)
        self.assertEqual(a.results["architect"][1]["status"], "INPUT_INVALID")
        a.close()
        self.root = tk.Tk()
        self.app = EAIDesktopApp(self.root, self.bridge)
        self.wait()
        self.assertEqual(self.app.limits.steps, 4)
        self.assertGreaterEqual(len(self.app.rows), 9)
        with patch("eai.desktop_app.filedialog.askopenfilename", return_value=str(saved)):
            self.app.open_problem("architect")
        self.wait()
        self.assertEqual(self.app.problem, saved)

    def test_navigation_during_worker_and_graceful_close(self):
        release = threading.Event()
        tick = []
        def bounded_work():
            release.wait(2)
            return {"status": "OK", "text": "completed"}
        self.app.run("home", "command", bounded_work)
        self.root.after(5, lambda: (tick.append(True), self.app.select("history")))
        self.root.after(45, release.set)
        self.wait()
        self.assertTrue(tick)
        self.assertEqual(self.app.page, "history")
        self.assertEqual(self.app.rows[0][1:], ("home", "command", "OK"))
        self.app.run("home", "command", bounded_work)
        self.app.close()
        self.root.mainloop()
        self.assertTrue(self.app.closing)
        self.app = None

    def test_selected_design_reaches_player_and_independent_receipt_check(self):
        a = self.app
        a.practice()
        self.wait()
        a.select("architect")
        a.design()
        self.wait()
        a.review_alternative()
        self.wait()
        self.assertEqual(a.page, "player")
        self.assertEqual(a.review["status"], "PURE_SYNTHETIC_PREVIEW_ONLY")
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            a.simulate()
        self.wait()
        self.assertEqual(a.results["player"][1]["replay"], "PURE_TRACE_REPLAY_MATCH_UNVERIFIED")
        a.select("architect")
        a.review_journey()
        self.wait()
        self.assertEqual(a.page, "verifier")
        self.assertEqual(a.results["verifier"][1]["candidate_count"], 2)
        self.assertEqual(a.results["verifier"][1]["independent_verification"], "NOT_ESTABLISHED")
