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
    widget.bind("<Tab>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
    widget.bind("<Shift-Tab>", lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[1])
    return widget


def result_text(parent, value, height=5):
    area = textbox(parent, height)
    area.insert("1.0", value)
    area.configure(state="disabled", highlightthickness=0, bg=parent.cget("bg"), padx=0, pady=0)
    bar = ttk.Scrollbar(parent, command=area.yview)
    area.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
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
    style.configure("Vertical.TScrollbar", background=LINE, troughcolor=PANEL, arrowcolor=MUTED,
                    borderwidth=0, arrowsize=11)
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)


def edit_problem(parent, original, on_apply):
    top = tk.Toplevel(parent, bg=BG)
    top.title("설계 초안 편집 · ProblemSpec")
    top.transient(parent)
    top.geometry(f"680x{min(700, parent.winfo_screenheight()-90)}")
    top.minsize(460, 420)
    top.grab_set()
    body = frame(top, padx=18, pady=12)
    body.pack(fill="both", expand=True)
    label(body, "설계 초안 편집", size=16, bold=True).pack(fill="x", pady=(0, 8))
    tabs = ttk.Notebook(body)
    tabs.pack(fill="both", expand=True)
    form, advanced = frame(tabs, PANEL, padx=12, pady=8), frame(tabs, PANEL, padx=10, pady=8)
    tabs.add(form, text="  목표와 조건  ")
    tabs.add(advanced, text="  전체 ProblemSpec  ")
    form.columnconfigure(1, weight=1)
    fields = {}
    for row, (key, title) in enumerate((("goal", "목표"), ("domain", "도메인 ID"),
            ("hard_constraints", "필수 조건 · 줄별 입력"), ("assumptions", "가정 · 줄별 입력"),
            ("risk", "위험도"), ("max_steps", "단계 예산 · 1–64"), ("max_seconds", "시간 예산 · 1–300초"))):
        label(form, title, fg=MUTED, size=9).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=4)
        if key in ("goal", "hard_constraints", "assumptions"):
            w = textbox(form, 2)
            fields[key] = w
        else:
            var = tk.StringVar(top)
            fields[key] = var
            w = combo(form, var, ("LOW", "MEDIUM", "HIGH")) if key == "risk" else entry(form, var)
        w.grid(row=row, column=1, sticky="ew", pady=4, ipady=2)
    label(form, "규칙으로 해석할 수 있는 조건은 must:전략ID 또는 forbid:전략ID입니다.",
          size=9, fg=MUTED, wrap=480).grid(row=7, columnspan=2, sticky="w", pady=7)
    raw = textbox(advanced, 13)
    raw.pack(fill="both", expand=True)
    error = label(body, "", fg=RED, size=9)
    error.pack(fill="x")
    buttons = frame(body)
    buttons.pack(fill="x", pady=(4, 0))
    base = dict(original)
    last_tab = [str(form)]

    def populate(data):
        for key, field in fields.items():
            value = data["budget"][key] if key.startswith("max_") else data[key]
            if isinstance(field, tk.Text):
                field.delete("1.0", "end")
                field.insert("1.0", "\n".join(value) if isinstance(value, list) else value)
            else:
                field.set(str(value))

    def read_form():
        data = dict(base)
        data["budget"] = {key: int(fields[key].get()) for key in ("max_steps", "max_seconds")}
        data.update(domain=fields["domain"].get().strip(), risk=fields["risk"].get(),
                    goal=fields["goal"].get("1.0", "end-1c").strip())
        for key in ("hard_constraints", "assumptions"):
            data[key] = [x.strip() for x in fields[key].get("1.0", "end-1c").splitlines() if x.strip()]
        ProblemSpec.validate(data)
        return data

    def read_raw():
        data = strict_json(raw.get("1.0", "end-1c"))
        ProblemSpec.validate(data)
        return data

    def sync(_event=None):
        selected = tabs.select()
        if selected == last_tab[0]:
            return
        try:
            data = read_form() if last_tab[0] == str(form) else read_raw()
        except (ValueError, TypeError, KeyError):
            tabs.select(last_tab[0])
            error.configure(text="목표, ID, 예산, 조건을 확인한 뒤 다시 시도해 주세요.")
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
            data = read_form() if tabs.select() == str(form) else read_raw()
        except (ValueError, TypeError, KeyError):
            error.configure(text="형식이 올바르지 않습니다. 목표, ID, 예산 범위를 확인하세요.")
            return
        on_apply(data)
        top.destroy()

    populate(base)
    tabs.bind("<<NotebookTabChanged>>", sync)
    button(buttons, "초안에 적용", apply, primary=True).pack(side="right")
    button(buttons, "닫기", top.destroy, quiet=True).pack(side="right", padx=8)
    top.bind("<Escape>", lambda e: top.destroy())
    fields["goal"].focus_set()
    return top
