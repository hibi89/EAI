"""Native Windows workstation for the local, CPU-owned EAI engine."""
from __future__ import annotations

import os
import json
from pathlib import Path
from functools import partial
from queue import Empty, Queue
import sqlite3
import sys
import threading
from tempfile import TemporaryDirectory
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

from .desktop_bridge import DesktopBridge
from .desktop_example import PracticeWorkspace
from .desktop_presentation import ERROR_TEXT, OPS, PAGES, caption
from .desktop_state import WorkspaceLimits
from .desktop_views import VIEWS
from .desktop_widgets import (AMBER, BG, FONT, LINE, MUTED, PANEL, PRIMARY, RAIL, RED,
                              SURFACE, TEAL, TEXT, VIOLET, button, edit_problem, frame,
                              label, setup_style, textbox)


def diagnostic(exc):
    if isinstance(exc, (OSError, KeyError)) and not isinstance(exc, sqlite3.Error):
        return "FILE_UNAVAILABLE"
    if isinstance(exc, sqlite3.Error):
        return "LOCAL_STORE_ERROR"
    if isinstance(exc, (ValueError, TypeError, OverflowError)):
        return "INPUT_INVALID"
    return "LOCAL_OPERATION_FAILED"


class EAIDesktopApp:
    def __init__(self, root, bridge=None):
        self.root = root
        self.bridge = bridge if bridge is not None else DesktopBridge()
        self.page = "home"
        self.rows = []
        self.limits = WorkspaceLimits()
        self.limit_vars = [tk.StringVar(root, v) for v in ("8", "60", "8")]
        self.results = {}
        self.example = None
        self.artifacts = None
        self.problem = self.library = self.plan = self.receipt = None
        self.draft = self.draft_review = self.review = self.catalog_data = self.node_data = None
        self.query = tk.StringVar(root)
        self.filter = tk.StringVar(root, "전체")
        self.stop_step = tk.StringVar(root, "끝까지")
        self.chosen_plan = tk.StringVar(root)
        self.busy = self.closing = False
        self.cancel_event = self.worker = None
        self.events: Queue[tuple] = Queue()
        self.nav = {}
        self.poll_id = None
        root.title("EAI · 로컬 워크스페이스")
        root.configure(bg=BG)
        root.geometry(f"{min(1240, root.winfo_screenwidth()-32)}x{min(820, root.winfo_screenheight()-84)}")
        root.minsize(760, 475)
        setup_style(root)
        self.build()
        self.select("home")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-l>", self.focus_command)
        root.bind("<Control-L>", self.focus_command)
        for i, key in enumerate(PAGES, 1):
            root.bind(f"<Alt-Key-{i}>", partial(self.select, key))
        root.bind_all("<MouseWheel>", self.wheel, add="+")
        self.run("home", "startup", lambda: {"status": "OK", "limits": self.bridge.state.limits()})
        self.poll_id = root.after(30, self.poll)

    def build(self):
        root = self.root
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        rail = frame(root, RAIL, padx=12, pady=14)
        rail.grid(row=0, column=0, sticky="nsew")
        brand = frame(rail)
        brand.pack(fill="x", pady=(0, 16))
        logo = tk.Canvas(brand, width=36, height=36, bg=RAIL, bd=0, highlightthickness=0)
        logo.pack(side="left", padx=(2, 7))
        for points, color in (((3, 12, 18, 4, 33, 12, 18, 20), VIOLET),
                              ((3, 19, 18, 27, 33, 19), "#9581e4"), ((3, 26, 18, 34, 33, 26), TEAL)):
            logo.create_line(*points, fill=color, width=3, joinstyle="round")
        label(brand, "EAI", size=21, bold=True).pack(side="left")
        label(brand, "v3.1", fg=MUTED, size=9).pack(side="left", padx=7, anchor="s", pady=7)
        label(rail, "작업 공간", size=9, fg=MUTED).pack(fill="x", padx=6, pady=(2, 6))
        for i, (key, (title, _, icon)) in enumerate(PAGES.items()):
            if i == 5:
                frame(rail, LINE, height=1).pack(fill="x", pady=9)
            row = frame(rail)
            row.pack(fill="x", pady=2)
            glyph = tk.Label(row, text=icon, bg=RAIL, fg=MUTED,
                             font=("Segoe MDL2 Assets", 13), width=2)
            glyph.pack(side="left")
            glyph.bind("<Button-1>", partial(self.select, key))
            b = button(row, title, lambda k=key: self.select(k), quiet=True, anchor="w", width=12)
            b.pack(side="left", expand=True, fill="x")
            self.nav[key] = (row, glyph, b)
        label(rail, "●  로컬 CPU", fg=TEAL, size=9).pack(side="bottom", anchor="w", padx=6)
        main = frame(root, BG, padx=14, pady=10)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        head = frame(main)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.heading = label(head, "", size=19, bold=True)
        self.heading.pack(side="left")
        self.english = label(head, "", fg=MUTED, size=10)
        self.english.pack(side="left", padx=12, anchor="s", pady=5)
        viewport = frame(main)
        viewport.grid(row=1, column=0, sticky="nsew")
        self.canvas = tk.Canvas(viewport, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(viewport, command=self.canvas.yview)
        def scroll_bounds(first, last):
            sb.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                sb.pack_forget()
            elif not sb.winfo_manager():
                sb.pack(side="right", fill="y", before=self.canvas)
        self.canvas.configure(yscrollcommand=scroll_bounds)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = frame(self.canvas, BG)
        self.body_id = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.body_id, width=e.width))
        root = self.root
        root.bind_all("<FocusIn>", self.reveal, add="+")
        dock = frame(main, "#1c2036", highlightthickness=1, highlightbackground="#665895", padx=11, pady=7)
        dock.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        top = frame(dock)
        top.pack(fill="x")
        label(top, "자연어 명령", bold=True).pack(side="left")
        self.status = label(top, "준비", size=9, fg=TEAL)
        self.status.pack(side="right")
        row = frame(dock)
        row.pack(fill="x", pady=(5, 3))
        self.command = textbox(row, 2)
        self.command.pack(side="left", fill="both", expand=True)
        actions = frame(row)
        actions.pack(side="left", padx=(6, 0))
        self.send = button(actions, "CPU 전송  ↵", self.ask, primary=True)
        self.send.pack(fill="x")
        self.newdraft = button(actions, "설계 초안", self.new_draft, quiet=True)
        self.newdraft.pack(fill="x")
        label(dock, "계산 · 비교 · 메모 · 도움말     |     Enter 전송    Shift+Enter 줄바꿈    Ctrl+L 입력", fg=MUTED, size=9).pack(fill="x")
        self.command.bind("<Return>", lambda e: (self.ask(), "break")[1])
        self.command.bind("<Shift-Return>", lambda e: (self.command.insert("insert", "\n"), "break")[1])
        self.command.bind("<Control-Return>", lambda e: (self.ask(), "break")[1])

    def wheel(self, event):
        if str(event.widget).startswith(str(self.body)) and not isinstance(event.widget, (tk.Text, ttk.Treeview, ttk.Combobox)):
            self.canvas.yview_scroll(-int(event.delta / 120) * 3, "units")

    def reveal(self, event):
        widget = event.widget
        if not str(widget).startswith(str(self.body)) or not widget.winfo_viewable():
            return
        height = self.body.winfo_height()
        top = widget.winfo_rooty() - self.body.winfo_rooty()
        first = self.canvas.canvasy(0)
        view = self.canvas.winfo_height()
        if top < first or top + widget.winfo_height() > first + view:
            self.canvas.yview_moveto(max(0, top-20) / max(1, height))

    def focus_command(self, _event=None):
        self.command.focus_set()
        return "break"

    def fill_command(self, value):
        self.command.delete("1.0", "end")
        self.command.insert("1.0", value)
        self.focus_command()

    def select(self, page, _event=None):
        self.page = page
        for key, (row, glyph, b) in self.nav.items():
            color = "#35304f" if key == page else RAIL
            row.configure(bg=color)
            glyph.configure(bg=color, fg=VIOLET if key == page else MUTED)
            b.configure(bg=color, highlightbackground=color, fg=TEXT if key == page else MUTED)
        self.heading.configure(text=PAGES[page][0])
        self.english.configure(text=PAGES[page][1])
        self.render()
        self.canvas.yview_moveto(0)

    def render(self):
        for child in self.body.winfo_children():
            child.destroy()
        VIEWS[self.page](self, self.body)

    def notice(self, message, color=AMBER):
        self.status.configure(text=message, fg=color)

    def ready(self):
        if self.busy:
            self.notice("현재 작업을 마친 뒤 다시 시도해 주세요.")
        return not self.busy and not self.closing

    def run(self, page, op, fn, *, cancel=None):
        if not self.ready():
            return
        self.busy, self.cancel_event = True, cancel
        self.notice(OPS.get(op, "작업 공간 열기") + " 진행 중…", VIOLET)
        self.send.configure(state="disabled")
        self.newdraft.configure(state="disabled")
        if cancel is not None:
            self.render()

        def work():
            try:
                data = fn()
            except Exception as exc:
                data = {"status": diagnostic(exc)}
            failed_journal = False
            rows = None
            try:
                if op != "startup":
                    self.bridge.state.record(page, op, data["status"])
                rows = self.bridge.state.history()
            except (OSError, ValueError, sqlite3.Error):
                failed_journal = True
            self.events.put((page, op, data, rows, failed_journal))

        self.worker = threading.Thread(target=work, name="EAI-local-worker")
        self.worker.start()

    def poll(self):
        try:
            page, op, data, rows, failed_journal = self.events.get_nowait()
        except Empty:
            pass
        else:
            if self.worker is not None:
                self.worker.join()
            self.busy, self.worker, self.cancel_event = False, None, None
            self.send.configure(state="normal")
            self.newdraft.configure(state="normal")
            if rows is not None:
                self.rows = rows
            code = data["status"]
            if op == "startup":
                if code == "OK":
                    self.apply_limits(data["limits"])
            else:
                self.results[page] = (op, data)
                self.apply_result(op, data)
            self.render()
            good = code in ("OK", "DRAFT_SAVED", "DRAFT_OPENED", "SETTINGS_SAVED", "EXAMPLE_READY")
            message = "준비" if op == "startup" and code == "OK" else caption(code)
            if failed_journal:
                message += " · 기록 읽기/저장 실패"
            self.notice(message, RED if failed_journal or code in ERROR_TEXT else TEAL if good else AMBER)
            if self.closing:
                self.destroy()
                return
        self.poll_id = self.root.after(30, self.poll)

    def apply_limits(self, limits):
        self.limits = limits
        for var, value in zip(self.limit_vars, (limits.steps, limits.seconds, limits.expansions)):
            var.set(str(value))

    def apply_result(self, op, data):
        code = data["status"]
        if op == "design":
            self.chosen_plan.set(next(iter(data.get("plan_specs", {})), ""))
        if op == "journey" and "path" in data:
            self.receipt = data.pop("path")
        if op == "plan" and "path" in data:
            self.plan = data.pop("path")
        if code == "EXAMPLE_READY":
            self.example = data.pop("workspace")
            self.problem, self.library = self.example.problem, self.example.library
            self.plan, self.receipt = self.example.plan, self.example.receipt
            self.draft = data.pop("draft")
            self.clear_library()
            self.clear_plan()
            self.results.pop("verifier", None)
        elif code in ("DRAFT_OPENED", "DRAFT_SAVED"):
            self.problem, self.draft = data.pop("path"), data.pop("draft")
            self.draft_review = self.bridge.draft_review(self.draft)
            self.clear_plan()
            if op == "draft_open" and self.page == "home":
                self.select("architect")
        elif code == "LOCAL_CATALOG_UNVERIFIED":
            self.catalog_data, self.node_data = data, None
        elif code == "NODE_DIGEST_MATCH":
            self.node_data = data
        elif op == "node":
            self.node_data = None
        elif op == "catalog":
            self.catalog_data = self.node_data = None
        elif op == "plan":
            self.review = data if "steps" in data else None
            self.stop_step.set("끝까지")
        elif code == "HOLD_PLAN_CHANGED":
            self.review = None
        elif code == "SETTINGS_SAVED":
            self.apply_limits(data.pop("limits"))

    def ask(self):
        if not self.ready():
            return
        command = self.command.get("1.0", "end-1c").strip()
        try:
            intent = self.bridge.rule_parser.parse(command)
        except ValueError:
            self.notice("명령 길이와 형식을 확인하세요. 최대 4,000자입니다.", RED)
            return
        # Unsupported freeform goals are staged for owner review, not executed.
        # The original command remains a local draft until explicitly saved.
        if intent.task == "unsupported":
            self.new_draft()
            return
        self.select("home")
        consent = False
        if intent.task == "remember":
            consent = messagebox.askyesno("로컬 메모 저장", "이 메모의 원문을 개인 SQLite에 보존할까요?", parent=self.root)
            if not consent:
                self.run("home", "command", lambda: {"status": "HOLD_NOTE_NOT_APPROVED", "text": "메모 저장을 취소했습니다."})
                return
        self.run("home", "command", lambda: self.bridge.ask(command, consent_to_note=consent))

    def new_draft(self):
        if not self.ready():
            return
        try:
            proposal = self.bridge.make_problem_draft(self.command.get("1.0", "end-1c"), max_steps=self.limits.steps,
                                                      max_seconds=self.limits.seconds)
        except ValueError:
            self.notice("설계 목표를 1~2,000자로 입력하세요.", RED)
            return
        self.draft, self.problem = proposal, None
        self.draft_review = self.bridge.draft_review(proposal)
        self.clear_plan()
        self.results.pop("architect", None)
        self.select("architect")
        self.notice("새 초안 · 조건을 검토하고 저장하세요.", VIOLET)

    def discover(self):
        if not self.ready() or self.draft is None:
            return
        current = dict(self.draft)
        chosen = self.library
        self.run("architect", "discover", lambda: self.bridge.discover_goal_capabilities(
            current, axnode_root=chosen))

    def edit(self):
        if not self.ready() or self.draft is None:
            return
        def apply(data):
            self.draft, self.problem = data, None
            self.draft_review = self.bridge.draft_review(data)
            self.clear_plan()
            self.results.pop("architect", None)
            self.render()
            self.notice("초안 수정됨 · 새 사본으로 저장하세요.", VIOLET)
        edit_problem(self.root, self.draft, apply)

    def save(self):
        if not self.ready() or self.draft is None:
            return
        raw = dict(self.draft, id="draft_" + uuid4().hex[:16])
        def save_copy():
            path = self.bridge.save_new_draft(raw)
            return {"status": "DRAFT_SAVED", "path": path, "draft": raw, "text": "개인 초안 폴더에 저장했습니다. 이 사본으로 설계 대안을 비교할 수 있습니다."}
        self.run("architect", "draft_save", save_copy)

    def open_problem(self, page):
        if not self.ready():
            return
        options = {}
        draft_folder = self.bridge.state_root / "drafts"
        from .local_files import local_path
        try:
            if local_path(draft_folder).is_dir():
                options["initialdir"] = str(draft_folder)
        except (OSError, ValueError):
            pass
        name = filedialog.askopenfilename(parent=self.root, title="로컬 ProblemSpec 열기", filetypes=[("ProblemSpec JSON", "*.json")], **options)
        if not name:
            return
        path = Path(name)
        self.select(page)
        def load():
            return {"status": "DRAFT_OPENED", "draft": self.bridge.load_draft(path),
                    "path": path, "text": "ProblemSpec 형식 검사를 통과했습니다."}
        self.run(page, "draft_open", load)

    def clear_plan(self):
        self.review = None
        self.stop_step.set("끝까지")
        self.results.pop("player", None)

    def clear_library(self):
        self.catalog_data = self.node_data = None
        self.results.pop("atlas", None)
        self.results.pop("architect", None)

    def choose_library(self):
        if not self.ready():
            return
        name = filedialog.askdirectory(parent=self.root, title="기존 AXNODE 저장소 선택", mustexist=True)
        if name:
            self.library = Path(name)
            self.clear_library()
            if self.page == "atlas":
                self.catalog()
            self.render()

    def choose(self, field):
        if not self.ready():
            return
        name = filedialog.askopenfilename(parent=self.root, title="로컬 JSON 선택", filetypes=[("JSON", "*.json")])
        if not name:
            return
        setattr(self, field, Path(name))
        if field == "plan":
            self.clear_plan()
        else:
            self.results.pop("verifier", None)
        self.render()

    def practice(self):
        if not self.ready():
            return
        previous = self.example
        def open_example():
            workspace = previous or PracticeWorkspace()
            return {"status": "EXAMPLE_READY", "workspace": workspace, "draft": self.bridge.load_draft(workspace.problem),
                    "text": "합성 목표, 노드 3개, 순수 계획, 검증 영수증을 열었습니다. 왼쪽에서 설계 대안, 노드 계보, 모의 실행, 영수증을 확인하세요."}
        self.run("home", "example", open_example)

    def design(self):
        if not self.problem or not self.library:
            self.notice("초안을 저장하거나 열고 AXNODE 저장소를 선택하세요.")
            return
        signal = threading.Event()
        p, lib, limit = self.problem, self.library, self.limits.expansions
        self.run("architect", "design", lambda: self.bridge.architect(p, lib, max_expansions=limit, cancelled=signal.is_set), cancel=signal)

    def request_cancel(self):
        if self.cancel_event:
            self.cancel_event.set()
            self.notice("다음 탐색 경계에서 중단 요청 확인 중…", AMBER)

    def stage_json(self, name, raw):
        # Called only by the single worker. Never publish into a chosen library.
        if self.artifacts is None:
            self.artifacts = TemporaryDirectory(prefix="eai-review-")
        file = Path(self.artifacts.name) / (name + "-" + uuid4().hex[:8] + ".json")
        with file.open("x", encoding="utf-8") as stream:
            json.dump(raw, stream, ensure_ascii=False)
        return file

    def review_alternative(self):
        if not self.ready():
            return
        design = self.results.get("architect", ("", {}))[1]
        raw = design.get("plan_specs", {}).get(self.chosen_plan.get())
        if raw is None or not self.problem:
            return
        source = self.problem
        self.clear_plan()
        self.select("player")
        def prepare():
            path = self.stage_json("plan", raw)
            return dict(self.bridge.inspect_plan(source, path), path=path)
        self.run("player", "plan", prepare)

    def review_journey(self):
        if not self.ready() or not self.problem or not self.library:
            return
        design = self.results.get("architect", ("", {}))[1]
        digest = design.get("problem_sha256")
        if digest is None:
            return
        source, library, expansions = self.problem, self.library, self.limits.expansions
        self.select("verifier")
        def prepare():
            raw = self.bridge.journey_receipt(source, library, max_expansions=expansions, expected_problem=digest)
            path = self.stage_json("journey", raw)
            return dict(self.bridge.verify_journey(path), path=path)
        self.run("verifier", "journey", prepare)

    def catalog(self):
        if not self.library:
            self.notice("조회할 기존 AXNODE 저장소를 선택하세요.")
            return
        lib, query, state = self.library, self.query.get(), self.filter.get()
        self.run("atlas", "catalog", lambda: self.bridge.axnode_catalog(lib, query=query, status="" if state == "전체" else state))

    def inspect_node(self, digest, _event=None):
        lib = self.library
        self.run("atlas", "node", lambda: self.bridge.node_detail(lib, digest))

    def inspect_plan(self):
        if not self.problem or not self.plan:
            self.notice("검토할 목표와 계획 파일을 선택하세요.")
            return
        p, plan = self.problem, self.plan
        self.run("player", "plan", lambda: self.bridge.inspect_plan(p, plan))

    def simulate(self):
        if not self.ready() or not self.review or self.review["status"] != "PURE_SYNTHETIC_PREVIEW_ONLY":
            return
        if not messagebox.askyesno("순수 시뮬레이션", "검토한 계획을 메모리 안에서 모의 실행할까요?", parent=self.root):
            self.notice("모의 실행을 시작하지 않았습니다.")
            return
        p, plan = self.problem, self.plan
        digests = (self.review["problem_sha256"], self.review["plan_sha256"])
        stop = None if self.stop_step.get() == "끝까지" else self.stop_step.get()
        self.run("player", "simulate", lambda: self.bridge.player(p, plan, acknowledged_pure_only=True,
                 reviewed_digests=digests, cancel_before_step=stop))

    def verify(self):
        if not self.receipt:
            self.notice("검사할 로컬 Journey 영수증을 선택하세요.")
            return
        path = self.receipt
        self.run("verifier", "verify", lambda: self.bridge.verify_journey(path))

    def set_limits(self):
        try:
            limits = WorkspaceLimits(*(int(var.get()) for var in self.limit_vars))
        except ValueError:
            self.notice("단계 1–64, 시간 1–300초, 검색 확장 1–8의 정수를 입력하세요.", RED)
            return
        def persist():
            self.bridge.state.set_limits(limits)
            return {"status": "SETTINGS_SAVED", "limits": limits}
        self.run("settings", "settings", persist)

    def close(self):
        if self.busy:
            self.closing = True
            self.request_cancel()
            self.notice("현재 작업을 정리한 뒤 종료합니다.")
        else:
            self.destroy()

    def destroy(self):
        if self.poll_id:
            self.root.after_cancel(self.poll_id)
        if self.example:
            self.example.close()
        if self.artifacts:
            self.artifacts.cleanup()
        self.root.destroy()


def main() -> int:
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    root = tk.Tk()
    if os.name == "nt":
        if getattr(sys, "frozen", False):
            icon = Path(getattr(sys, "_MEIPASS")) / "assets" / "eai_desktop.ico"
        else:
            icon = Path(__file__).resolve().parents[1] / "scripts" / "eai_desktop.ico"
        if icon.is_file():
            root.iconbitmap(default=str(icon))
    EAIDesktopApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
