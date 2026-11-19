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

    def test_v32_reviewed_goal_to_real_two_distinct_architect_plans(self):
        w = self.fixture()
        source = json.loads(w.problem.read_text(encoding="utf-8"))
        source.update(goal="로컬 후보의 검토 단계를 비교하라", oracle="owner.local.oracle",
                      state_refs=["synthetic.local.1"],
                      hard_constraints=["forbid:unsafe.operation"],
                      objectives=["검증 가능한 두 경로 확인"], permissions=["pure", "local.read"])
        before = {p.relative_to(w.library): hashlib.sha256(p.read_bytes()).digest()
                  for p in w.library.rglob("*") if p.is_file()}
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network blocked")):
            out = self.bridge.architect_reviewed_goal(source, w.library, owner_reviewed=True)
        self.assertEqual(out["status"], "TWO_PLANS_ADVISORY_UNVERIFIED")
        self.assertEqual(out["engine_status"], "CANDIDATES_UNVERIFIED")
        self.assertEqual(len(out["plan_specs"]), 2)
        self.assertNotEqual(tuple(out["source_sets"][0]), tuple(out["source_sets"][1]))
        self.assertEqual({p.relative_to(w.library): hashlib.sha256(p.read_bytes()).digest()
                          for p in w.library.rglob("*") if p.is_file()}, before)
        self.assertFalse((self.root / "drafts").exists())
        self.assertNotIn(source["goal"], json.dumps(out, ensure_ascii=False))
        self.assertFalse(out["can_execute"])
        self.assertEqual(out["external_actions"], 0)
        self.assertEqual(out["execution"], "NOT_EXECUTED")
        for plan in out["plan_specs"].values():
            self.assertEqual(plan["problem_sha256"], out["problem_sha256"])
            self.assertTrue(all(step["operator"] == "synthetic.noop.v1" for step in plan["steps"]))

    def test_v32_reviewed_goal_missing_inputs_and_integrity_fail_closed(self):
        w = self.fixture()
        source = json.loads(w.problem.read_text(encoding="utf-8"))
        source.update(oracle="owner.local.oracle", state_refs=["synthetic.local.1"],
                      hard_constraints=["forbid:unsafe.operation"], permissions=["pure", "local.read"])
        self.assertEqual(self.bridge.architect_reviewed_goal(source, w.library)["status"],
                         "HOLD_OWNER_REVIEW_REQUIRED")
        self.assertEqual(self.bridge.architect_reviewed_goal(
            dict(source, oracle="owner_review_required"), w.library,
            owner_reviewed=True)["status"], "HOLD_INCOMPLETE_PROBLEM")
        self.assertEqual(self.bridge.architect_reviewed_goal(
            dict(source, permissions=["pure"]), w.library,
            owner_reviewed=True)["status"], "HOLD_LOCAL_READ_NOT_APPROVED")
        self.assertEqual(self.bridge.architect_reviewed_goal(
            source, None, owner_reviewed=True)["status"], "HOLD_LOCAL_LIBRARY_REQUIRED")
        conflict = self.bridge.architect_reviewed_goal(
            dict(source, hard_constraints=["must:practice.review", "forbid:practice.review"]),
            w.library, owner_reviewed=True)
        self.assertEqual(conflict["status"], "HOLD_DISTINCT_PLANS_NOT_ESTABLISHED")
        self.assertIn("CONTRADICTORY_HARD_CONSTRAINTS", conflict["blockers"])
        self.assertEqual(conflict["plan_specs"], {})
        unsupported = self.bridge.architect_reviewed_goal(
            dict(source, domain="absent"), w.library, owner_reviewed=True)
        self.assertEqual(unsupported["status"], "HOLD_DISTINCT_PLANS_NOT_ESTABLISHED")
        self.assertIn("INSUFFICIENT_DISTINCT_LOCAL_STRATEGIES", unsupported["blockers"])
        cancelled = self.bridge.architect_reviewed_goal(source, w.library, owner_reviewed=True,
                                                       cancelled=lambda: True)
        self.assertEqual(cancelled["status"], "HOLD_DISTINCT_PLANS_NOT_ESTABLISHED")
        self.assertEqual(cancelled["engine_status"], "CANCELLED")
        with self.assertRaises(ValueError):
            self.bridge.architect_reviewed_goal(source, self.root / "not_created",
                                                owner_reviewed=True)
        self.assertFalse((self.root / "not_created").exists())

    def test_v32_selected_plan_policy_revalidates_goal_and_pinned_sources(self):
        w = self.fixture()
        source = json.loads(w.problem.read_text(encoding="utf-8"))
        source.update(goal="검토 가능한 순수 노드 대안", risk="LOW",
                      oracle="owner.local.oracle", state_refs=["synthetic.local.1"],
                      hard_constraints=["forbid:unsafe.operation"],
                      objectives=["선택 경로 정책 검사"], permissions=["pure", "local.read"])
        report = self.bridge.architect_reviewed_goal(source, w.library, owner_reviewed=True)
        self.assertEqual(report["status"], "TWO_PLANS_ADVISORY_UNVERIFIED")
        selected = next(iter(report["plan_specs"]))
        outcome = self.bridge.inspect_reviewed_selection(source, report, selected, w.library)
        self.assertEqual(outcome["status"], "PURE_SYNTHETIC_PREVIEW_ONLY")
        self.assertTrue(outcome["preview_only"])
        self.assertFalse(outcome["can_execute_real_actions"])
        self.assertEqual(outcome["original_writes"], 0)
        self.assertEqual(outcome["execution"], "NOT_EXECUTED")
        self.assertEqual(outcome["steps"][0][1], "synthetic.noop.v1")
        self.assertEqual(outcome["source_sha256"], report["source_sets"][0])
        changed = self.bridge.inspect_reviewed_selection(dict(source, goal="다른 목표"), report,
                                                          selected, w.library)
        self.assertEqual(changed["status"], "HOLD_PLAN_CHANGED")
        self.assertEqual(changed["reasons"], ["STALE_OR_UNREVIEWED_DESIGN"])
        copy = dict(report, source_sets=[list(x) for x in report["source_sets"]])
        copy["source_sets"][0][0] = "0" * 64
        self.assertEqual(self.bridge.inspect_reviewed_selection(
            source, copy, selected, w.library)["status"], "HOLD_PLAN_CHANGED")
        self.assertEqual(self.bridge.inspect_reviewed_selection(
            source, report, "option.not_here", w.library)["status"], "HOLD_PLAN_CHANGED")
        high = dict(source, risk="MEDIUM")
        revised = self.bridge.architect_reviewed_goal(high, w.library, owner_reviewed=True)
        held = self.bridge.inspect_reviewed_selection(high, revised, selected, w.library)
        self.assertEqual(held["status"], "HOLD_POLICY_DENIED")
        self.assertIn("NON_LOW_RISK", held["reasons"])
        self.assertFalse(held["preview_only"])
        self.assertFalse((self.root / "drafts").exists())

    def test_v32_pure_player_replay_boundaries_cancel_and_no_consent(self):
        w = self.fixture()
        source = json.loads(w.problem.read_text(encoding="utf-8"))
        source.update(goal="확인한 노드를 순수 모의 검토", risk="LOW", oracle="owner.local.oracle",
                      state_refs=["synthetic.local.1"], objectives=["검토 결과 추적"],
                      hard_constraints=["forbid:unsafe.operation"], permissions=["pure", "local.read"])
        design = self.bridge.architect_reviewed_goal(source, w.library, owner_reviewed=True)
        selected = next(iter(design["plan_specs"]))
        review = self.bridge.inspect_reviewed_selection(source, design, selected, w.library)
        denied = self.bridge.play_reviewed_pure_plan(source, design, review, w.library)
        self.assertEqual(denied["status"], "HOLD_PURE_SIMULATION_CONFIRMATION")
        self.assertEqual(denied["execution"], "NOT_EXECUTED")
        before = {p.relative_to(w.library): hashlib.sha256(p.read_bytes()).digest()
                  for p in w.library.rglob("*") if p.is_file()}
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network")):
            flow = self.bridge.play_reviewed_pure_plan(
                source, design, review, w.library, acknowledged_pure_only=True)
        self.assertEqual(flow["status"], "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED")
        self.assertEqual(flow["replay"], "PURE_TRACE_REPLAY_MATCH_UNVERIFIED")
        self.assertEqual(flow["execution"], "PURE_SYNTHETIC_NOOP_ONLY")
        self.assertEqual(len(flow["step_observations"]), flow["interpreted_steps"])
        self.assertTrue(all(r["status"] == "PURE_NOOP_INTERPRETED_NOT_VERIFIED"
                            for r in flow["step_observations"]))
        self.assertEqual(flow["external_actions"], 0)
        self.assertEqual(flow["original_writes"], 0)
        self.assertFalse(flow["can_promote"])
        self.assertFalse(flow["verified_real_world"])
        self.assertEqual(before, {p.relative_to(w.library): hashlib.sha256(p.read_bytes()).digest()
                                  for p in w.library.rglob("*") if p.is_file()})
        first = design["plan_specs"][selected]["steps"][0]["id"]
        cancelled = self.bridge.play_reviewed_pure_plan(
            source, design, review, w.library, acknowledged_pure_only=True,
            cancel_before_step=first)
        self.assertEqual(cancelled["status"], "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED")
        self.assertEqual(cancelled["interpreted_steps"], 0)
        self.assertEqual(cancelled["step_observations"], [])
        tamper = dict(review, plan_sha256="0"*64)
        self.assertEqual(self.bridge.play_reviewed_pure_plan(
            source, design, tamper, w.library,
            acknowledged_pure_only=True)["status"], "HOLD_PLAN_CHANGED")
        self.assertFalse((self.root / "drafts").exists())

    def test_v32_private_library_creation_and_node_import_do_not_mutate_original(self):
        self.assertEqual(self.bridge.create_fresh_private_library()["status"], "HOLD_PRIVATE_LIBRARY_CONSENT")
        self.assertFalse((self.root / "libraries").exists())
        w = self.fixture()
        src = next(path for path in (w.library / "nodes").glob("*.axnode")
                   if not json.loads(path.read_text(encoding="utf-8"))["parent_hashes"])
        before = hashlib.sha256(src.read_bytes()).hexdigest()
        res = self.bridge.create_fresh_private_library(owner_approved=True)
        self.assertTrue(res["created"])
        self.assertEqual(res["node_count"], 0)
        self.assertEqual(res["external_actions"], 0)
        with closing(sqlite3.connect(res["path"] / "axnodes.sqlite")) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))
        self.assertEqual(self.bridge.import_private_candidate(res["path"], src)["status"],
                         "HOLD_PRIVATE_IMPORT_CONSENT")
        imported = self.bridge.import_private_candidate(res["path"], src, owner_approved=True)
        self.assertEqual(imported["node_count"], 1)
        self.assertEqual(imported["authority"], "DRAFT_OR_CANDIDATE_ONLY_NO_ACTIVE")
        self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(), before)
        with self.assertRaises(ValueError):
            self.bridge.import_private_candidate(w.library, src, owner_approved=True)
        self.assertEqual(self.bridge.axnode_catalog(res["path"])["shown"], 1)

    def test_v32_discovery_only_reports_real_local_registry_and_evidence(self):
        plain = self.bridge.make_problem_draft("아무 제한 없이 모든 것을 자동화해줘")
        result = self.bridge.discover_goal_capabilities(plain)
        self.assertEqual(result["status"], "NO_TYPED_CPU_MATCH")
        self.assertEqual(len(result["available_typed_domains"]), 13)
        self.assertEqual(result["node_candidates"], [])
        self.assertEqual(result["execution"], "NOT_EXECUTED")
        self.assertEqual(result["external_actions"], 0)
        self.assertFalse(result["plan_verified"])
        typed = dict(plain, domain="csv_quality")
        result = self.bridge.discover_goal_capabilities(typed)
        self.assertEqual(result["status"], "TYPED_DOMAIN_MATCH_UNVERIFIED")
        self.assertEqual(result["matched_typed_domain"], "csv_quality")
        w = self.fixture()
        goal = dict(plain, goal="revision", permissions=["pure"])
        locked = self.bridge.discover_goal_capabilities(goal, w.library)
        self.assertEqual(locked["library_status"], "HOLD_LOCAL_READ_NOT_APPROVED")
        allowed = self.bridge.discover_goal_capabilities(dict(goal, permissions=["pure", "local.read"]), w.library)
        self.assertEqual(allowed["library_status"], "LOCAL_HINTS_UNVERIFIED")
        self.assertTrue(any(n["node_id"] == "practice.revision" for n in allowed["node_candidates"]))
        self.assertTrue(all(n["provenance"] == "LOCAL_CANDIDATE_UNVERIFIED" for n in allowed["node_candidates"]))
        self.assertFalse((self.root / "drafts").exists())

    def test_v32_guided_draft_review_is_honest_and_never_grants_write(self):
        raw = self.bridge.make_problem_draft("인력 일정을 분석하고 대안을 비교해줘")
        review = self.bridge.draft_review(raw)
        self.assertEqual(review["status"], "REVIEW_REQUIRED")
        self.assertEqual(review["permission_scope"], ["pure"])
        self.assertEqual(set(review["missing"]), {
            "NO_EVIDENCE_REFS", "NO_OBJECTIVES", "ORACLE_NOT_DEFINED", "NO_EXPLICIT_CONSTRAINTS"})
        self.assertFalse(review["truth_verified"])
        self.assertEqual(review["external_actions"], 0)
        self.assertFalse((self.root / "drafts").exists())
        ready = dict(raw, oracle="owner_defined_oracle", state_refs=["local.evidence.1"],
                     objectives=["누락 일정이 없는지 검사"], hard_constraints=["기간 내 변경 불가"])
        self.assertEqual(self.bridge.draft_review(ready)["status"], "FORM_COMPLETE_UNVERIFIED")
        self.assertFalse(self.bridge.draft_review(ready)["truth_verified"])
        with self.assertRaises(ValueError):
            self.bridge.draft_review(dict(raw, permissions=["pure", "write.original"]))
        with self.assertRaises(ValueError):
            self.bridge.draft_review(dict(raw, state_refs=["/tmp/secret.txt"]))

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

    def test_freeform_goal_routes_into_reviewable_architect_draft(self):
        goal = "작업 일정의 제약조건을 분석하고 두 설계를 비교해줘"
        self.app.fill_command(goal)
        self.app.ask()
        self.assertEqual(self.app.page, "architect")
        self.assertEqual(self.app.draft["goal"], goal)
        self.assertEqual(self.app.draft["permissions"], ["pure"])
        self.assertIsNone(self.app.problem)
        self.assertFalse((self.bridge.state_root / "drafts").exists())
        self.assertIsNone(self.app.review)

    def test_v32_edited_problem_preview_keeps_missing_evidence_explicit(self):
        self.app.fill_command("제약조건과 근거를 비교해줘")
        self.app.new_draft()
        self.assertEqual(self.app.page, "architect")
        self.assertEqual(self.app.draft_review["status"], "REVIEW_REQUIRED")
        self.assertIn("NO_OBJECTIVES", self.app.draft_review["missing"])
        self.assertFalse((self.bridge.state_root / "drafts").exists())

    def test_v32_gui_goal_to_real_architect_without_file_ritual(self):
        w = PracticeWorkspace()
        self.addCleanup(w.close)
        self.app.fill_command("실제 로컬 전략 후보를 비교해줘")
        self.app.new_draft()
        self.app.library = w.library
        self.app.draft.update(domain="practice", oracle="owner.local.oracle",
                              state_refs=["synthetic.local.1"],
                              hard_constraints=["forbid:unsafe.operation"],
                              objectives=["두 후보를 비교"], permissions=["pure", "local.read"])
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            self.app.design()
        self.wait()
        self.assertEqual(self.app.results["architect"][0], "design")
        data = self.app.results["architect"][1]
        self.assertEqual(data["status"], "TWO_PLANS_ADVISORY_UNVERIFIED")
        self.assertEqual(len(data["plan_specs"]), 2)
        self.assertFalse((self.bridge.state_root / "drafts").exists())
        self.assertIsNone(self.app.problem)
        self.assertFalse(data["can_execute"])
        self.assertEqual(self.app.rows[0][3], "TWO_PLANS_ADVISORY_UNVERIFIED")

    def test_v32_gui_reviewed_plan_to_policy_no_auto_simulation(self):
        w = PracticeWorkspace()
        self.addCleanup(w.close)
        self.app.fill_command("선택한 순수 전략 검토")
        self.app.new_draft()
        self.app.library = w.library
        self.app.draft.update(domain="practice", risk="LOW", oracle="owner.local.oracle",
                              state_refs=["synthetic.local.1"],
                              hard_constraints=["forbid:unsafe.operation"],
                              objectives=["후보 검토"], permissions=["pure", "local.read"])
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            self.app.design()
        self.wait()
        report = self.app.results["architect"][1]
        self.assertEqual(report["status"], "TWO_PLANS_ADVISORY_UNVERIFIED")
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            self.app.review_alternative()
        self.wait()
        self.assertEqual(self.app.page, "player")
        self.assertEqual(self.app.review["status"], "PURE_SYNTHETIC_PREVIEW_ONLY")
        self.assertFalse(self.app.review["can_execute_real_actions"])
        self.assertIsNone(self.app.plan)
        self.assertIsNone(self.app.problem)
        self.assertNotIn("simulate", [op for _,_,op,_ in self.app.rows])
        with patch("eai.desktop_app.messagebox.askyesno", return_value=False):
            self.app.simulate()
        self.assertNotIn("simulate", [op for _,_,op,_ in self.app.rows])
        self.assertFalse((self.bridge.state_root / "drafts").exists())

    def test_v32_gui_pure_player_trace_after_separate_confirmation(self):
        w = PracticeWorkspace()
        self.addCleanup(w.close)
        self.app.fill_command("순수 단계 관찰")
        self.app.new_draft()
        self.app.library = w.library
        self.app.draft.update(domain="practice", risk="LOW", oracle="owner.local.oracle",
                              state_refs=["synthetic.local.1"],
                              hard_constraints=["forbid:unsafe.operation"],
                              objectives=["영수증 생성"], permissions=["pure", "local.read"])
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            self.app.design()
        self.wait()
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            self.app.review_alternative()
        self.wait()
        self.assertEqual(self.app.review["status"], "PURE_SYNTHETIC_PREVIEW_ONLY")
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            self.app.simulate()
        self.wait()
        out = self.app.results["player"][1]
        self.assertEqual(out["status"], "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED")
        self.assertEqual(out["replay"], "PURE_TRACE_REPLAY_MATCH_UNVERIFIED")
        self.assertEqual(len(out["step_observations"]), out["interpreted_steps"])
        self.assertEqual(out["original_writes"], 0)
        self.assertEqual(out["external_actions"], 0)
        self.assertFalse((self.bridge.state_root / "drafts").exists())

    def test_v32_gui_consent_creates_only_fresh_private_library(self):
        with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
            self.app.create_library()
        self.wait()
        self.assertEqual(self.app.page, "atlas")
        self.assertTrue(self.app.library.is_dir())
        self.assertEqual(self.app.results["atlas"][1]["status"], "PRIVATE_EMPTY_LIBRARY_CREATED")
        self.assertEqual(self.bridge.axnode_catalog(self.app.library)["shown"], 0)

    def test_v32_discovery_button_runs_local_preview_only(self):
        self.app.fill_command("새로운 서비스 구현 방법을 알려줘")
        self.app.new_draft()
        self.app.discover()
        self.wait()
        self.assertEqual(self.app.results["architect"][0], "discover")
        self.assertEqual(self.app.results["architect"][1]["status"], "NO_TYPED_CPU_MATCH")
        self.assertEqual(self.app.results["architect"][1]["execution"], "NOT_EXECUTED")
        self.assertFalse((self.bridge.state_root / "drafts").exists())

    def test_v32_guided_editor_applies_owner_oracle_and_safe_read_scope(self):
        from tkinter import ttk
        from eai.desktop_widgets import edit_problem
        proposal = self.bridge.make_problem_draft("합성 작업 최적화")
        captured = []
        dialog = edit_problem(self.root, proposal, captured.append)
        body = dialog.winfo_children()[0]
        notebook = next(child for child in body.winfo_children() if isinstance(child, ttk.Notebook))
        evidence = dialog.nametowidget(notebook.tabs()[1])
        objectives = evidence.grid_slaves(row=0, column=1)[0]
        oracle = evidence.grid_slaves(row=1, column=1)[0]
        refs = evidence.grid_slaves(row=2, column=1)[0]
        objectives.insert("1.0", "지표를 검증한다")
        oracle.delete(0, "end")
        oracle.insert(0, "owner_defined_oracle")
        refs.insert("1.0", "synthetic.local.1")
        local_read = evidence.grid_slaves(row=5, column=1)[0]
        local_read.invoke()
        apply_button = next(child for child in body.winfo_children()[-1].winfo_children()
                            if isinstance(child, tk.Button) and "적용" in child.cget("text"))
        apply_button.invoke()
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["oracle"], "owner_defined_oracle")
        self.assertEqual(captured[0]["objectives"], ["지표를 검증한다"])
        self.assertEqual(captured[0]["state_refs"], ["synthetic.local.1"])
        self.assertEqual(captured[0]["permissions"], ["pure", "local.read"])
        self.assertFalse((self.bridge.state_root / "drafts").exists())

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
        self.assertEqual(self.app.page, "architect")
        self.assertEqual(self.app.draft["goal"], "지원 밖 임의 요청")
        self.assertIsNone(self.app.problem)
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
