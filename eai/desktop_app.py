"""EAI V3.1 native dark workstation; stdlib Tkinter, no web server.

Launch with `python -m eai.desktop_app` or bundled Windows EAI.exe.
The UI does not mint approval, enable Hydrogen, run arbitrary shell commands,
or treat an unverified Architect/Player preview as real-world execution.
"""
from __future__ import annotations

import json
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .desktop_bridge import DesktopBridge
from .contracts import ProblemSpec, strict_json

BG = "#0a1020"
PANEL = "#111b30"
PANEL2 = "#17243b"
EDGE = "#273651"
TEXT = "#e8eefc"
MUTED = "#94a6c6"
PURPLE = "#7966ea"
CYAN = "#49d5cd"
AMBER = "#e8bb68"
RED = "#ee777b"


class EAIDesktopApp:
    TABS = ("현황", "Architect", "AXNODE", "Verifier", "Player", "기록")

    def __init__(self, root: tk.Tk, bridge: DesktopBridge | None = None):
        self.root = root
        self.bridge = bridge if bridge is not None else DesktopBridge()
        self.problem_path: str | None = None
        self.store_path: str | None = None
        self.plan_path: str | None = None
        self.report_path: str | None = None
        self.last_draft: dict | None = None
        self.last_catalog: dict | None = None
        self.last_result: dict | None = None
        self.records: list[tuple[str, str]] = []
        self.events: Queue = Queue()
        self.busy = False
        self.tab = "현황"
        self.nav_buttons: dict[str, tk.Button] = {}
        self.path_labels: dict[str, tk.Label] = {}
        root.title("EAI V3.1 — Independent Local AI")
        root.configure(bg=BG)
        root.geometry("1440x860")
        root.minsize(950, 650)
        root.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self._select("현황")
        root.after(100, self._poll)

    def _label(self, parent, text: str, *, size: int = 11, color: str = TEXT,
               bold: bool = False, **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

    def _button(self, parent, text: str, command, *, accent=False, width=None):
        options = dict(text=text, command=command, bd=0, relief="flat", cursor="hand2",
                       bg=PURPLE if accent else PANEL2, fg="#ffffff" if accent else TEXT,
                       activebackground="#6555ce" if accent else "#22324e",
                       activeforeground="white", padx=13, pady=10,
                       font=("Segoe UI", 10, "bold"))
        if width is not None:
            options["width"] = width
        return tk.Button(parent, **options)

    def _build(self):
        header = tk.Frame(self.root, bg=BG, height=72)
        header.pack(side="top", fill="x", padx=22, pady=(12, 10))
        header.pack_propagate(False)
        self._label(header, "⬡  EAI V3.1", size=20, bold=True).pack(side="left")
        self._label(header, "  ·  Independent Architect / Player / AXNODE",
                    color=MUTED).pack(side="left", padx=10)
        for name, color in (("HYDROGEN HOLD", RED), ("EXTERNAL OFF", AMBER),
                            ("LOCAL CPU", CYAN)):
            pill = tk.Label(header, text=name, bg=PANEL, fg=color,
                            padx=11, pady=9, font=("Segoe UI", 10, "bold"))
            pill.pack(side="right", padx=5)

        work = tk.Frame(self.root, bg=BG)
        work.pack(side="top", fill="both", expand=True, padx=20)
        sidebar = tk.Frame(work, bg=PANEL, width=188, highlightthickness=1,
                           highlightbackground=EDGE)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)
        self._label(sidebar, "WORKSPACE", color=MUTED, size=9, bold=True).pack(
            anchor="w", padx=17, pady=(22, 16))
        for tab in self.TABS:
            button = self._button(sidebar, tab, lambda tab=tab: self._select(tab))
            button.configure(anchor="w", width=17, padx=15)
            button.pack(fill="x", padx=9, pady=3)
            self.nav_buttons[tab] = button
        tk.Frame(sidebar, bg=EDGE, height=1).pack(fill="x", padx=15, pady=20)
        self._label(sidebar, "권한 / 보안", bold=True).pack(anchor="w", padx=17)
        self._label(sidebar, "외부 전송 · 비활성\n실제 Player · 승인 필요\nAXNODE · 읽기/검토",
                    color=MUTED, justify="left", size=10).pack(
                        anchor="w", padx=17, pady=12)

        main = tk.Frame(work, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        metrics = tk.Frame(main, bg=BG)
        metrics.pack(fill="x", pady=(0, 12))
        for title, value, color in (
            ("컴퓨팅", "CPU 우선", CYAN),
            ("원격 모델", "OFF / HOLD", RED),
            ("실제 실행", "별도 승인", AMBER),
            ("검증 상태", "미인수", MUTED),
        ):
            card = tk.Frame(metrics, bg=PANEL, highlightthickness=1,
                            highlightbackground=EDGE)
            card.pack(side="left", fill="both", expand=True, padx=(0, 8))
            self._label(card, title, size=9, color=MUTED).pack(anchor="w", padx=16, pady=(13, 1))
            self._label(card, value, size=14, color=color, bold=True).pack(
                anchor="w", padx=16, pady=(0, 14))

        center = tk.Frame(main, bg=PANEL, highlightbackground=EDGE,
                          highlightthickness=1)
        center.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.title = self._label(center, "", size=15, bold=True)
        self.title.pack(anchor="w", padx=20, pady=(17, 5))
        self.description = self._label(center, "", color=MUTED, justify="left", wraplength=590)
        self.description.pack(anchor="w", fill="x", padx=20)
        self.result = tk.Text(center, bg="#0e172a", fg=TEXT,
                              insertbackground=TEXT, selectbackground="#3a4679",
                              wrap="word", bd=0, relief="flat", padx=17, pady=15,
                              font=("Consolas", 10), height=14)
        self.result.pack(fill="both", expand=True, padx=14, pady=(14, 14))
        self.result.configure(state="disabled")
        self.graph = tk.Canvas(center, bg="#0e172a", bd=0,
                               highlightthickness=0, height=175)

        right = tk.Frame(main, bg=PANEL, width=264, highlightbackground=EDGE,
                         highlightthickness=1)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self._label(right, "로컬 입력 · 파일 연결", size=13, bold=True).pack(
            anchor="w", padx=16, pady=(18, 9))
        pickers = (
            ("problem", "ProblemSpec JSON", self._pick_problem),
            ("store", "AXNODE 폴더", self._pick_store),
            ("plan", "PlanSpec JSON", self._pick_plan),
            ("report", "검증 보고서 JSON", self._pick_report),
        )
        for key, name, callback in pickers:
            self._button(right, "선택 · " + name, callback).pack(
                fill="x", padx=13, pady=(8, 0))
            lbl = self._label(right, "선택 안 됨", color=MUTED, size=9,
                              anchor="w")
            lbl.pack(fill="x", padx=17, pady=(3, 3))
            self.path_labels[key] = lbl
        tk.Frame(right, bg=EDGE, height=1).pack(fill="x", padx=13, pady=(13, 8))
        self.action_title = self._label(right, "기능", color=MUTED, bold=True)
        self.action_title.pack(anchor="w", padx=17, pady=4)
        self.actions = tk.Frame(right, bg=PANEL)
        self.actions.pack(fill="x", padx=13)
        self._label(right, "실행은 GUI 입력 → 기존 EAI 계약\n→ 실패 시 HOLD. 별도 권한을\n자동으로 생성하지 않습니다.",
                    color=MUTED, size=9, justify="left").pack(
                        anchor="w", padx=16, pady=(18, 0))

        composer = tk.Frame(self.root, bg=PANEL, highlightthickness=1,
                            highlightbackground="#483e83")
        composer.pack(side="bottom", fill="x", padx=20, pady=(12, 16))
        top = tk.Frame(composer, bg=PANEL)
        top.pack(fill="x", padx=15, pady=(9, 5))
        self._label(top, "자연어 명령 입력", bold=True, color=TEXT).pack(side="left")
        self.state = self._label(top, "준비 · 외부 전송 없음", color=CYAN, size=9)
        self.state.pack(side="right")
        line = tk.Frame(composer, bg=PANEL)
        line.pack(fill="x", padx=15, pady=(0, 13))
        self.command = tk.Text(line, height=3, wrap="word", bg="#0d172b", fg=TEXT,
                               insertbackground=TEXT, selectbackground="#3a4679",
                               font=("Segoe UI", 11), bd=0, relief="flat", padx=11, pady=10)
        self.command.pack(side="left", fill="x", expand=True)
        buttons = tk.Frame(line, bg=PANEL)
        buttons.pack(side="right", padx=(9, 0))
        self._button(buttons, "CPU 답변", self._ask, accent=True).pack(fill="x", pady=(0, 7))
        self._button(buttons, "설계 초안", self._draft).pack(fill="x")
        self.command.bind("<Control-Return>", lambda _e: self._ask())

    def _select(self, tab: str):
        self.tab = tab
        for label, button in self.nav_buttons.items():
            button.configure(bg=PURPLE if label == tab else PANEL2)
        descriptions = {
            "현황": "로컬 독립 EAI. 숫자·명령·설계는 별도 검증 전에는 확정 사실이 아닙니다.",
            "Architect": "선택한 ProblemSpec과 기존 AXNODE를 이용한 CPU 계획 후보 미리보기. 실제 실행 없음.",
            "AXNODE": "선택한 기존 SQLite 카탈로그의 메타데이터만 읽기 전용 조회합니다.",
            "Verifier": "오프라인 Journey 영수증 무결성 검사. 독립적인 현실 검증과는 구분합니다.",
            "Player": "사용자가 승인한 순수 메모리 no-op만 시뮬레이션합니다. 실제 OS 작업 불가.",
            "기록": "현재 GUI 세션의 요약 상태만 표시합니다. 비밀정보·명령 원문 기록 안 함.",
        }
        self.title.configure(text=tab + "  /  EAI LOCAL")
        self.description.configure(text=descriptions[tab])
        for widget in self.actions.winfo_children():
            widget.destroy()
        buttons = {
            "현황": (("명령 사용법", self._help), ("설계 초안 저장", self._save_draft)),
            "Architect": (("Architect 설계 미리보기", self._architect),
                          ("설계 초안 저장", self._save_draft),
                          ("초안 JSON 편집", self._edit_draft)),
            "AXNODE": (("AXNODE 검색", self._catalog),),
            "Verifier": (("보고서 무결성 검사", self._verify),),
            "Player": (("순수 시뮬레이션", self._player),),
            "기록": (("상태 이력 보기", self._show_history),),
        }[tab]
        for name, action in buttons:
            self._button(self.actions, name, action, accent=name.endswith("미리보기")).pack(
                fill="x", pady=5)
        if tab == "AXNODE":
            self.graph.pack(fill="x", padx=14, pady=(0, 12))
            self._draw_graph()
        else:
            self.graph.pack_forget()
        self._display_text({"status": "READY", "page": tab,
                            "help": descriptions[tab]}, save=False)

    def _display_text(self, payload: dict, *, save: bool = True):
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(rendered) > 16000:
            rendered = rendered[:16000] + "\n... (표시 제한, 원본은 수정하지 않음)"
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("1.0", rendered)
        self.result.configure(state="disabled")
        if save:
            self.last_result = payload
            status = str(payload.get("status", "LOCAL"))
            self.records.append((self.tab, status[:80]))
            del self.records[:-100]
            self.state.configure(text=status[:45], fg=CYAN if status == "READY" else AMBER)

    def _read_command(self) -> str:
        command = self.command.get("1.0", "end-1c").strip()
        if not command or len(command) > 4000:
            raise ValueError("1..4000자 명령을 입력하세요")
        return command

    def _submit(self, job):
        if self.busy:
            return
        self.busy = True
        self.state.configure(text="CPU 작업 중...", fg=AMBER)
        def target():
            try:
                result = job()
                self.events.put(("result", result))
            except Exception as exc:
                # No arbitrary raw exception strings: they may contain private paths.
                self.events.put(("error", type(exc).__name__))
        threading.Thread(target=target, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, result = self.events.get_nowait()
                self.busy = False
                if kind == "error":
                    self._display_text({"status": "HOLD_LOCAL_ERROR", "error_type": result,
                                        "external_calls": 0})
                elif isinstance(result, dict):
                    if result.get("kind") == "AXNODE":
                        self.last_catalog = result
                        if self.tab == "AXNODE":
                            self._draw_graph()
                    self._display_text(result)
                else:
                    self._display_text({"status": "HOLD_UNEXPECTED_RESULT"})
        except Empty:
            pass
        self.root.after(100, self._poll)

    def _ask(self):
        try:
            command = self._read_command()
            intent = self.bridge.rule_parser.parse(command)
        except ValueError as exc:
            messagebox.showwarning("명령 확인", str(exc), parent=self.root)
            return
        approved = False
        if intent.task == "remember":
            approved = messagebox.askyesno("로컬 메모 저장 승인",
                "이 문장을 사용자 전용 로컬 SQLite 메모로 저장할까요?", parent=self.root)
            if not approved:
                self._display_text({"status": "HOLD_NOTE_NOT_APPROVED"})
                return
        self._submit(lambda: self.bridge.ask(command, consent_to_note=approved))

    def _draft(self):
        try:
            proposal = self.bridge.make_problem_draft(self._read_command())
        except ValueError as exc:
            messagebox.showwarning("초안 확인", str(exc), parent=self.root)
            return
        self.last_draft = proposal
        self._select("Architect")
        self._display_text({"status": "DRAFT_UNVERIFIED_REVIEW_REQUIRED",
                            "problem_spec": proposal,
                            "note": "자동 승인되지 않습니다. 저장 전 제약·위험·검증 기준을 검토하세요."})

    def _edit_draft(self):
        if self.last_draft is None:
            messagebox.showinfo("초안", "하단의 '설계 초안'을 먼저 사용하세요.", parent=self.root)
            return
        popup = tk.Toplevel(self.root, bg=BG)
        popup.title("ProblemSpec — 로컬 JSON 편집")
        popup.geometry("760x590")
        area = tk.Text(popup, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                       font=("Consolas", 10), wrap="word", padx=12, pady=12)
        area.pack(fill="both", expand=True, padx=15, pady=15)
        area.insert("1.0", json.dumps(self.last_draft, ensure_ascii=False, indent=2))
        def apply_changes():
            try:
                raw = strict_json(area.get("1.0", "end-1c"))
                ProblemSpec.validate(raw)
            except (ValueError, TypeError) as exc:
                messagebox.showerror("계약 불일치", type(exc).__name__, parent=popup)
                return
            self.last_draft = raw
            self._display_text({"status": "DRAFT_REVIEWED_NOT_EXECUTED",
                                "problem_spec": raw,
                                "note": "저장 버튼을 누르기 전까지 파일 변경 없음."})
            popup.destroy()
        self._button(popup, "JSON 검증 · 초안 반영", apply_changes, accent=True).pack(
            fill="x", padx=15, pady=(0, 15))
        popup.transient(self.root)
        popup.grab_set()

    def _save_draft(self):
        if self.last_draft is None:
            messagebox.showinfo("설계 초안", "하단 입력창에서 '설계 초안'을 먼저 누르세요.", parent=self.root)
            return
        if not messagebox.askyesno("파일 생성 확인",
                "사용자 전용 새 ProblemSpec 파일을 생성할까요? 기존 파일은 덮어쓰지 않습니다.",
                parent=self.root):
            return
        self._submit(lambda: {"status": "DRAFT_SAVED_PRIVATE_LOCAL",
                              "file": str(self.bridge.save_new_draft(self.last_draft)),
                              "execution": "NOT_EXECUTED"})

    def _pick_problem(self):
        self._pick_file("problem", "problem_path", ("ProblemSpec JSON", "*.json"))

    def _pick_plan(self):
        self._pick_file("plan", "plan_path", ("PlanSpec JSON", "*.json"))

    def _pick_report(self):
        self._pick_file("report", "report_path", ("Journey JSON", "*.json"))

    def _pick_file(self, key, attr, filetype):
        value = filedialog.askopenfilename(parent=self.root, title="로컬 파일 선택",
                                           filetypes=[filetype, ("모든 파일", "*.*")])
        if value:
            setattr(self, attr, value)
            self.path_labels[key].configure(text=Path(value).name[:34], fg=CYAN)

    def _pick_store(self):
        value = filedialog.askdirectory(parent=self.root, title="기존 AXNODE 폴더 선택")
        if value:
            self.store_path = value
            self.path_labels["store"].configure(text=Path(value).name[:34], fg=CYAN)

    def _require(self, *attrs):
        if not all(getattr(self, attr) for attr in attrs):
            messagebox.showwarning("입력 필요", "오른쪽에서 필요한 로컬 파일/폴더를 먼저 선택하세요.",
                                   parent=self.root)
            return False
        return True

    def _architect(self):
        if self._require("problem_path", "store_path"):
            self._submit(lambda: self.bridge.architect(self.problem_path, self.store_path))

    def _catalog(self):
        if not self._require("store_path"):
            return
        phrase = self.command.get("1.0", "end-1c").strip()
        self._submit(lambda: self.bridge.axnode_catalog(self.store_path, query=phrase[:120]))

    def _verify(self):
        if self._require("report_path"):
            self._submit(lambda: self.bridge.verify_journey(self.report_path))

    def _player(self):
        if not self._require("problem_path", "plan_path"):
            return
        yes = messagebox.askyesno("순수 시뮬레이션만 허용",
                 "실제 파일·외부 시스템 작업이 없는 synthetic.noop.v1 시뮬레이션만 실행합니다. 계속할까요?",
                 parent=self.root)
        if yes:
            self._submit(lambda: self.bridge.player(
                self.problem_path, self.plan_path, acknowledged_pure_only=True))

    def _show_history(self):
        self._display_text({"status": "LOCAL_SESSION_ONLY", "records": [
            {"panel": p, "status": s} for p, s in self.records[-60:]],
            "note": "원본 명령과 비밀정보는 GUI 상태 기록에 저장하지 않습니다."}, save=False)

    def _help(self):
        self._display_text({"status": "SUPPORTED_LOCAL_INPUTS", "examples": [
            "계산: 12 * (3 + 4)", "비교: a=1, b=2", "도움말",
            "기억해: 로컬 메모 (별도 확인 필요)",
            "자유 목표: '설계 초안' 후 ProblemSpec 확인 및 Architect 미리보기"],
            "disallowed": ["임의 Python/셸 실행", "자동 클라우드 송신", "실제 Player 실행", "무단 파일 덮어쓰기"]})

    def _draw_graph(self):
        import math
        can = self.graph
        can.delete("all")
        w = max(500, can.winfo_width())
        h = 175
        nodes = (self.last_catalog or {}).get("nodes", [])[:16]
        if not nodes:
            can.create_text(w//2, h//2, text="AXNODE 조회 후 제한된 관계 그래프를 표시합니다",
                            fill=MUTED, font=("Segoe UI", 10))
            return
        coords = {}
        for i, n in enumerate(nodes):
            angle = i * 2 * math.pi / len(nodes)
            coords[n["sha256"]] = (w//2 + 0.38*w*math.cos(angle),
                                    h//2 + 58*math.sin(angle))
        for n in nodes:
            x,y = coords[n["sha256"]]
            for parent in n["parents"]:
                if parent in coords:
                    px,py = coords[parent]
                    can.create_line(px, py, x, y, fill="#394e72", width=2)
        for n in nodes:
            x,y = coords[n["sha256"]]
            can.create_oval(x-13,y-13,x+13,y+13,fill=PURPLE,outline=CYAN)
            can.create_text(x,y+23,text=n["node_id"][:18],fill=TEXT,
                            font=("Segoe UI", 8))

    def _close(self):
        if self.busy:
            messagebox.showwarning("작업 진행 중", "현재 로컬 작업 종료 후 닫을 수 있습니다.",
                                   parent=self.root)
            return
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    EAIDesktopApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
