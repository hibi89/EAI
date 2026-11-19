"""Shared native workstation controls and a structured ProblemSpec editor."""
import json
import tkinter as tk
from tkinter import ttk

from .contracts import ProblemSpec, strict_json

BG = "#0e1422"
RAIL = "#111827"
PANEL = "#182133"
SURFACE = "#202c42"
LINE = "#324058"
TEXT = "#eff2fc"
MUTED = "#afbdd2"
VIOLET = "#a698ff"
PRIMARY = "#5e4ba9"
TEAL = "#69d8bf"
AMBER = "#f1c57f"
RED = "#ffa5ab"
FONT = "Malgun Gothic"
MONO = "Consolas"


def frame(parent, color=None, **kw):
    return tk.Frame(parent, bg=color or parent.cget("bg"), **kw)


def label(parent, text, *, size=10, fg=TEXT, bold=False, mono=False, wrap=0, **kw):
    return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=fg, anchor="w", justify="left",
                    font=(MONO if mono else FONT, size, "bold" if bold else "normal"),
                    wraplength=wrap, **kw)


def button(parent, text, fn, *, primary=False, quiet=False, **kw):
    bg = PRIMARY if primary else (parent.cget("bg") if quiet else SURFACE)
    widget = tk.Button(parent, text=text, command=fn, bg=bg, fg=TEXT, activebackground="#494170",
                       activeforeground=TEXT, disabledforeground="#9ba7ba", relief="flat", bd=0,
                       highlightthickness=1, highlightcolor=VIOLET, highlightbackground=bg,
                       font=(FONT, 10), padx=11, pady=5, takefocus=True, cursor="hand2", **kw)
    widget.bind("<Return>", lambda e: (widget.invoke(), "break")[1])
    return widget


def card(parent, title=None):
    box = frame(parent, PANEL, highlightbackground=LINE, highlightthickness=1, padx=14, pady=10)
    if title:
        label(box, title, size=11, bold=True).pack(fill="x", pady=(0, 7))
    return box


def entry(parent, variable, width=22):
    return tk.Entry(parent, textvariable=variable, width=width, bg=BG, fg=TEXT,
                    insertbackground=TEXT, selectbackground=PRIMARY, relief="flat", bd=0,
                    highlightthickness=1, highlightbackground=LINE, highlightcolor=VIOLET,
                    font=(FONT, 10))


def combo(parent, variable, values, width=15):
    return ttk.Combobox(parent, textvariable=variable, values=values, state="readonly",
                        width=width, font=(FONT, 10))


def textbox(parent, height=3):
    widget = tk.Text(parent, bg=BG, fg=TEXT, insertbackground=TEXT, wrap="word", padx=10, pady=6,
                     selectbackground=PRIMARY, relief="flat", bd=0, highlightthickness=1,
                     highlightbackground=LINE, highlightcolor=VIOLET, height=height, width=12,
                     font=(FONT, 10), undo=True)
    def traverse(event):
        target = widget.tk_focusPrev() if event.state & 1 else widget.tk_focusNext()
        if target is not None:
            target.focus_set()
        return "break"
    widget.bind("<Tab>", traverse)
    widget.bind("<Shift-Tab>", traverse)
    return widget


def result_text(parent, value, height=5):
    area = textbox(parent, height)
    area.insert("1.0", value)
    area.configure(state="disabled", highlightthickness=0, bg=parent.cget("bg"), padx=0, pady=0)
    bar = ttk.Scrollbar(parent, command=area.yview)
    def scrolled(first, last):
        bar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            bar.pack_forget()
        elif not bar.winfo_manager():
            bar.pack(side="right", fill="y", before=area)
    area.configure(yscrollcommand=scrolled)
    area.pack(fill="both", expand=True)
    return area


def setup_style(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(FONT, 10), background=PANEL, foreground=TEXT)
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=int(24 * float(root.tk.call("tk", "scaling")) / 1.33) + 5,
                    borderwidth=0)
    style.configure("Treeview.Heading", background=SURFACE, foreground=MUTED,
                    font=(FONT, 9, "bold"), padding=(5, 3))
    style.map("Treeview", background=[("selected", PRIMARY)], foreground=[("selected", "white")])
    style.configure("TCombobox", arrowcolor=TEXT, fieldbackground=BG)
    style.map("TCombobox", fieldbackground=[("readonly", BG)], foreground=[("readonly", TEXT)])
    style.configure("TScrollbar", background=LINE, troughcolor=PANEL, arrowcolor=MUTED,
                    bordercolor=PANEL, lightcolor=LINE, darkcolor=LINE, borderwidth=0, arrowsize=11)
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)


def edit_problem(parent, original, on_apply):
    """Guided, bounded ProblemSpec editor; no raw JSON needed for normal goals."""
    top = tk.Toplevel(parent, bg=BG)
    top.title("설계 초안 · 목표·검증 기준·접근 권한")
    top.transient(parent)
    top.geometry(f"770x{min(730, parent.winfo_screenheight()-90)}")
    top.minsize(530, 430)
    top.grab_set()
    body = frame(top, padx=18, pady=12)
    body.pack(fill="both", expand=True)
    label(body, "설계 초안 검토", size=16, bold=True).pack(fill="x", pady=(0, 4))
    label(body, "저장 또는 설계 실행 전, 근거·검증 기준·읽기 권한을 직접 확인합니다.",
          fg=MUTED, wrap=680).pack(fill="x", pady=(0, 6))
    tabs = ttk.Notebook(body)
    tabs.pack(fill="both", expand=True)
    scope = frame(tabs, PANEL, padx=12, pady=8)
    evidence = frame(tabs, PANEL, padx=12, pady=8)
    advanced = frame(tabs, PANEL, padx=10, pady=8)
    tabs.add(scope, text="  목표·자원  ")
    tabs.add(evidence, text="  근거·권한·검증  ")
    tabs.add(advanced, text="  고급 JSON  ")
    scope.columnconfigure(1, weight=1)
    evidence.columnconfigure(1, weight=1)
    fields = {}

    def field(form, row, key, title, *, multiline=False, choices=None, height=2):
        label(form, title, fg=MUTED, size=9).grid(row=row, column=0, sticky="nw", padx=(0, 10), pady=5)
        if multiline:
            w = textbox(form, height)
            fields[key] = w
        else:
            var = tk.StringVar(top)
            fields[key] = var
            w = combo(form, var, choices) if choices else entry(form, var)
        w.grid(row=row, column=1, sticky="ew", pady=3, ipady=2)
        return w

    field(scope, 0, "goal", "해결하려는 목표", multiline=True, height=4)
    field(scope, 1, "domain", "작업 도메인 ID")
    field(scope, 2, "hard_constraints", "절대 지켜야 할 조건 (한 줄에 하나)", multiline=True)
    field(scope, 3, "risk", "위험 분류", choices=("LOW", "MEDIUM", "HIGH"))
    field(scope, 4, "max_steps", "최대 단계 (1–64)")
    field(scope, 5, "max_seconds", "최대 실행시간 (1–300초)")
    label(scope, "유형화된 규칙은 must:전략ID / forbid:전략ID로 표기합니다.",
          fg=MUTED, size=9, wrap=510).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)

    field(evidence, 0, "objectives", "성공 조건/목적 (한 줄에 하나)", multiline=True)
    field(evidence, 1, "oracle", "검증 기준 ID 또는 owner_review_required")
    field(evidence, 2, "state_refs", "로컬 근거 참조 ID (한 줄에 하나)", multiline=True)
    field(evidence, 3, "assumptions", "아직 확인하지 않은 가정 (한 줄에 하나)", multiline=True)
    label(evidence, "기본 권한", fg=MUTED, size=9).grid(row=4, column=0, sticky="w", pady=6)
    label(evidence, "pure · 외부 행동 및 원본 변경 불가", fg=TEAL, size=9).grid(
        row=4, column=1, sticky="w")
    local_read = tk.BooleanVar(top, value=False)
    tk.Checkbutton(evidence, text="승인한 로컬 근거 읽기 허용 (local.read)", variable=local_read,
                   bg=PANEL, fg=TEXT, selectcolor=BG, activebackground=PANEL,
                   activeforeground=TEXT, takefocus=True).grid(row=5, column=1, sticky="w", pady=5)
    label(evidence, "파일 선택과 실제 실행 권한은 별도입니다. 외부 전송·원본 쓰기는 허용하지 않습니다.",
          fg=AMBER, size=9, wrap=470).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)

    raw = textbox(advanced, 16)
    raw.pack(fill="both", expand=True)
    error = label(body, "", fg=RED, size=9)
    error.pack(fill="x")
    buttons = frame(body)
    buttons.pack(fill="x", pady=(4, 0))
    base = dict(original)
    last_tab = [str(scope)]

    def populate(data):
        for key, widget in fields.items():
            value = data["budget"][key] if key.startswith("max_") else data[key]
            if isinstance(widget, tk.Text):
                widget.delete("1.0", "end")
                widget.insert("1.0", "\n".join(value) if isinstance(value, list) else value)
            else:
                widget.set(str(value))
        local_read.set("local.read" in data["permissions"])

    def read_form():
        data = dict(base)
        data["budget"] = {key: int(fields[key].get()) for key in ("max_steps", "max_seconds")}
        data.update(goal=fields["goal"].get("1.0", "end-1c").strip(),
                    domain=fields["domain"].get().strip(), risk=fields["risk"].get(),
                    oracle=fields["oracle"].get().strip(),
                    permissions=["pure"] + (["local.read"] if local_read.get() else []))
        for key in ("hard_constraints", "assumptions", "objectives", "state_refs"):
            data[key] = [line.strip() for line in fields[key].get("1.0", "end-1c").splitlines()
                         if line.strip()]
        ProblemSpec.validate(data)
        return data

    def read_raw():
        data = strict_json(raw.get("1.0", "end-1c"))
        ProblemSpec.validate(data)
        return data

    def sync(_event=None):
        selected = tabs.select()
        previous = last_tab[0]
        if selected == previous:
            return
        if selected == str(advanced) or previous == str(advanced):
            try:
                data = read_raw() if previous == str(advanced) else read_form()
            except (ValueError, TypeError, KeyError):
                tabs.select(previous)
                error.configure(text="입력한 목표·근거 ID·예산·검증 기준 또는 JSON 형식을 확인하세요.")
                return
            base.update(data)
            if selected == str(advanced):
                raw.delete("1.0", "end")
                raw.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
            else:
                populate(data)
        last_tab[0] = selected
        error.configure(text="")

    def apply():
        try:
            data = read_raw() if tabs.select() == str(advanced) else read_form()
        except (ValueError, TypeError, KeyError):
            error.configure(text="잘못된 입력입니다. 목표, 증거, 검증 기준, 예산과 권한을 확인하세요.")
            return
        on_apply(data)
        top.destroy()

    populate(base)
    tabs.bind("<<NotebookTabChanged>>", sync)
    button(buttons, "검토한 초안 적용", apply, primary=True).pack(side="right")
    button(buttons, "취소 · 저장 안 함", top.destroy, quiet=True).pack(side="right", padx=8)
    top.bind("<Escape>", lambda e: top.destroy())
    fields["goal"].focus_set()
    return top
