"""Seven native workstation pages. Each action calls the same desktop controller."""
import tkinter as tk
from functools import partial
from tkinter import ttk

from .desktop_presentation import OPS, PAGES, caption, explain, timestamp
from .desktop_widgets import (AMBER, BG, LINE, MUTED, PANEL, PRIMARY, TEAL, TEXT, VIOLET,
                              button, card, combo, entry, frame, label, result_text)


def action_row(parent, *actions):
    row = frame(parent)
    row.pack(fill="x", pady=(4, 1))
    for title, fn, primary in actions:
        button(row, title, fn, primary=primary).pack(side="left", padx=(0, 6))
    return row


def selection(parent, title, path, fn):
    row = frame(parent)
    row.pack(fill="x", pady=2)
    label(row, title, fg=MUTED, size=9, width=13).pack(side="left")
    button(row, "선택", fn, quiet=True).pack(side="right")
    label(row, path.name[:56] if path else "선택한 자료 없음", size=10).pack(side="left", fill="x", expand=True)


def result(app, parent, page, height=6):
    last = app.results.get(page)
    if not last:
        return
    op, data = last
    box = card(parent, OPS[op] + "  ·  " + caption(data["status"]))
    box.pack(fill="x", pady=(9, 0))
    result_text(box, explain(op, data), height)


def history_table(app, parent, rows, height=5, resume=False):
    tree = ttk.Treeview(parent, columns=("time", "action", "status"), show="headings", height=height)
    for key, name, width in (("time", "시간", 118), ("action", "작업", 146), ("status", "결과", 240)):
        tree.heading(key, text=name, anchor="w")
        tree.column(key, width=width, minwidth=80, anchor="w")
    for i, (stamp, page, op, code) in enumerate(rows):
        tree.insert("", "end", iid=str(i), values=(timestamp(stamp), OPS[op], caption(code)))
    def select(_=None):
        if tree.selection():
            page = rows[int(tree.selection()[0])][1]
            app.select(page)
    if resume:
        tree.bind("<Double-1>", select)
        tree.bind("<Return>", select)
    bar = ttk.Scrollbar(parent, command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    tree.pack(fill="x", expand=True)
    return tree


def home(app, parent):
    stats = frame(parent)
    stats.pack(fill="x")
    items = (("입력 엔진", "CPU 규칙", TEAL, "\ue950"), ("외부 송신", "꺼짐", TEAL, "\ue72e"),
             ("Player", "모의 전용", VIOLET, "\ue768"), ("작업 기록", f"{len(app.rows)}건", VIOLET, "\ue81c"))
    for i, (name, value, accent, glyph) in enumerate(items):
        stats.columnconfigure(i, weight=1, uniform="stat")
        item = card(stats)
        item.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
        head = frame(item)
        head.pack(fill="x")
        tk.Label(head, text=glyph, font=("Segoe MDL2 Assets", 12),
                 bg=PANEL, fg=accent).pack(side="left", padx=(0, 6))
        label(head, name, size=9, fg=MUTED).pack(side="left")
        label(item, value, size=14, bold=True).pack(fill="x", pady=(4, 0))

    center = frame(parent)
    center.pack(fill="x", pady=(10, 0))
    center.columnconfigure(0, weight=3, uniform="work")
    center.columnconfigure(1, weight=2, uniform="work")
    console = card(center)
    console.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
    label(console, "목표 분석 · CPU 결과", size=12, bold=True).pack(fill="x")
    last = app.results.get("home")
    if last:
        op, data = last
        label(console, OPS[op] + "  /  " + caption(data["status"]), size=9, fg=TEAL, wrap=325).pack(fill="x")
        result_text(frame_for_text(console), explain(op, data), 5)
    else:
        label(console, "지원하는 명령", fg=MUTED, size=9).pack(fill="x", pady=(6, 3))
        for title, sample in (("계산", "계산: 12 * (3 + 4)"), ("비교", "비교: A=12, B=18"),
                              ("메모", "메모목록")):
            line = frame(console, "#141d2d")
            line.pack(fill="x", pady=1)
            label(line, title, fg=VIOLET, size=9).pack(side="left", padx=7)
            button(line, sample, lambda s=sample: app.fill_command(s), quiet=True, anchor="w").pack(
                side="left", expand=True, fill="x")
    quick = card(center, "작업 시작")
    quick.grid(row=0, column=1, sticky="nsew")
    for title, note, action, primary in (
            ("내 목표 설계 시작", "하단 목표를 검토 가능한 설계 초안으로 변환", app.new_draft, True),
            ("로컬 예제 열기", "합성 목표 · 노드 3개 · 계획 · 영수증", app.practice, False),
            ("저장한 초안 열기", "지난 목표와 조건을 이어서 편집", lambda: app.open_problem("architect"), False),
            ("내 개인 세션 복구", "저장된 마지막 목표 초안만 다시 불러오기 · 실행 권한 없음", app.resume_review_session, False)):
        button(quick, title, action, primary=primary, anchor="w").pack(fill="x", pady=(3, 0))
        label(quick, note, size=9, fg=MUTED, wrap=220).pack(fill="x", pady=(2, 5))

    flow = card(parent, "실제 작업 흐름 · 자동 실행 아님")
    flow.pack(fill="x", pady=(9, 0))
    lane = frame(flow)
    lane.pack(fill="x")
    for i, (key, title) in enumerate((("architect", "목표 설계"), ("atlas", "근거 탐색"),
                                      ("player", "계획 검토"), ("verifier", "영수증 검사"))):
        lane.columnconfigure(i * 2, weight=1, uniform="flow")
        button(lane, title, lambda k=key: app.select(k)).grid(row=0, column=i*2, sticky="ew")
        if i < 3:
            label(lane, "›", fg=VIOLET, size=14).grid(row=0, column=i*2+1, padx=3)
    label(flow, "목표와 근거를 직접 확인 → 대안을 선택 → 순수 no-op만 별도 승인 → 해시 재현 검증 → 개인 후보 기록."
          " 각 단계의 진실성은 독립적으로 검증되지 않았습니다.", fg=MUTED, wrap=690).pack(fill="x", pady=(8, 0))
    recent = card(parent, "최근 작업")
    recent.pack(fill="x", pady=(9, 0))
    if app.rows:
        history_table(app, recent, app.rows[:5], min(5, len(app.rows)), True)
    else:
        label(recent, "첫 명령을 보내면 시각과 결과가 표시됩니다.", fg=MUTED).pack(anchor="w")


def architect(app, parent):
    box = card(parent, "목표와 조건")
    box.pack(fill="x")
    if app.draft:
        d = app.draft
        label(box, d["goal"][:240], wrap=560, bold=True).pack(fill="x")
        label(box, f"{d['domain']}   ·   위험도 {d['risk']}   ·   {d['budget']['max_steps']}단계 / {d['budget']['max_seconds']}초"
              f"   ·   조건 {len(d['hard_constraints'])}개   ·   가정 {len(d['assumptions'])}개", fg=MUTED, wrap=560).pack(fill="x")
        reviewed = app.bridge.draft_review(d)
        if reviewed["missing"]:
            label(box, "확인이 필요한 항목: " + ", ".join({
                "NO_EVIDENCE_REFS": "실제 근거 참조 미지정",
                "NO_OBJECTIVES": "성공 조건 미설정",
                "ORACLE_NOT_DEFINED": "검증 기준 미확정",
                "NO_EXPLICIT_CONSTRAINTS": "필수 조건 미작성",
            }[key] for key in reviewed["missing"]), fg=AMBER, wrap=570).pack(fill="x", pady=(6, 1))
        else:
            label(box, "필드 형식만 확인됨 · 근거와 진실성 검증 전", fg=TEAL).pack(fill="x", pady=(6, 1))
        label(box, "권한: " + ", ".join(reviewed["permission_scope"]) +
              f" · 증거 참조 {reviewed['evidence_ref_count']}개 · 목적 {reviewed['objective_count']}개",
              fg=MUTED).pack(fill="x")
    else:
        label(box, "하단에 목표를 적고 ‘설계 초안’을 누르거나 저장한 ProblemSpec을 여세요.", fg=MUTED, wrap=570).pack(fill="x")
    row = action_row(box, ("초안 열기", lambda: app.open_problem("architect"), False))
    scope = action_row(box, ("현재 가능한 CPU 기능·근거 확인", app.discover, True))
    if not app.draft:
        for child in scope.winfo_children():
            child.configure(state="disabled")
    for name, fn in (("초안 편집", app.edit), ("새 사본 저장", app.save),
                     ("개인 세션 보존", app.save_review_session)):
        b = button(row, name, fn)
        b.pack(side="left", padx=(0, 6))
        if not app.draft:
            b.configure(state="disabled")
    files = card(parent, "설계 대안 비교")
    files.pack(fill="x", pady=(9, 0))
    selection(files, "AXNODE 저장소", app.library, app.choose_library)
    button(files, "개인 AXNODE 라이브러리 만들기", app.create_library).pack(anchor="w", pady=3)
    label(files, "검토한 목표를 실제 로컬 Architect로 분석합니다. 근거가 부족하면 이유를 표시합니다.",
          size=9, fg=MUTED).pack(fill="x")
    row = action_row(files, ("대안 비교", app.design, True))
    if app.busy and app.cancel_event:
        button(row, "탐색 중단 요청", app.request_cancel).pack(side="left")
    result(app, parent, "architect", 7)
    design = app.results.get("architect", ("", {}))[1]
    if design.get("kind") == "REVIEWED_GOAL_ARCHITECT" and design.get("comparison"):
        for candidate in design["comparison"]:
            summary = card(parent, "후보 검토 · " + candidate["id"])
            summary.pack(fill="x", pady=(7, 0))
            label(summary, "실제 로컬 자료 기반 · 단계 " + str(candidate["declared_steps"]) +
                  "개 · 시간 상한 " + str(candidate["declared_seconds_upper_bound"]) + "초",
                  fg=TEAL).pack(fill="x")
            label(summary, "전략: " + ", ".join(candidate["strategy_refs"]) +
                  " · 연산자: " + ", ".join(candidate["operators"]),
                  wrap=580, fg=MUTED).pack(fill="x")
            for tradeoff in candidate["tradeoffs"]:
                label(summary, "주의 · " + tradeoff, fg=AMBER, wrap=560).pack(fill="x")
            label(summary, "근거 SHA-256: " + ", ".join(candidate["evidence_hashes"]),
                  fg=MUTED, wrap=570, size=9).pack(fill="x")
            label(summary, "실제 정답/복구 가능성: " + candidate["independent_accuracy"] +
                  " / " + candidate["reversibility"], fg=AMBER, wrap=560).pack(fill="x")
    if "problem_sha256" in design:
        row = frame(parent)
        row.pack(fill="x", pady=6)
        choices = list(design.get("plan_specs", {}))
        if choices:
            combo(row, app.chosen_plan, choices, width=23).pack(side="left", padx=(0, 6))
            button(row, "Player에서 검토", app.review_alternative).pack(side="left", padx=(0, 6))
        button(row, "영수증 재계산", app.review_journey).pack(side="left")


def atlas(app, parent):
    box = card(parent, "로컬 라이브러리")
    box.pack(fill="x")
    selection(box, "AXNODE 저장소", app.library, app.choose_library)
    controls = action_row(box, ("새 개인 라이브러리 만들기", app.create_library, True))
    button(controls, "로컬 후보 1개 가져오기", app.import_candidate).pack(side="left", padx=(6, 0))
    label(box, "기존 저장소는 읽기 전용 · 가져오기는 EAI가 새로 만든 개인 저장소만 허용", fg=MUTED,
          size=9, wrap=540).pack(fill="x")
    row = frame(box)
    row.pack(fill="x", pady=4)
    label(row, "검색", size=9, fg=MUTED).pack(side="left", padx=(0, 7))
    search = entry(row, app.query)
    search.pack(side="left", fill="x", expand=True, ipady=5)
    search.bind("<Return>", lambda e: app.catalog())
    combo(row, app.filter, ("전체", "DRAFT", "CANDIDATE"), width=12).pack(side="left", padx=7)
    button(row, "조회", app.catalog, primary=True).pack(side="right")
    if app.catalog_data is not None:
        data = app.catalog_data
        nodes = data["nodes"]
        box = card(parent, f"조회 결과 {data['shown']}개   ·   전체 {data['total_nodes']}개" +
                   ("   ·   최대 200개 표시" if data["truncated"] else ""))
        box.pack(fill="x", pady=(9, 0))
        tree = ttk.Treeview(box, columns=("id", "v", "state", "type"), show="headings", height=min(5, max(1, len(nodes))))
        for key, name, width in (("id", "노드", 200), ("v", "버전", 52), ("state", "상태", 105), ("type", "출력", 110)):
            tree.heading(key, text=name, anchor="w")
            tree.column(key, width=width, minwidth=34, anchor="w")
        for n in nodes:
            tree.insert("", "end", iid=n["sha256"], values=(n["node_id"], n["version"], n["status"], n["output_type"]))
        area = frame(box)
        area.pack(side="bottom", fill="x")
        def details(_=None):
            if tree.selection():
                app.inspect_node(tree.selection()[0])
        tree.bind("<Return>", details)
        tree.bind("<Double-1>", details)
        if nodes:
            tree.selection_set(nodes[0]["sha256"])
            button(area, "선택한 노드 상세", details, quiet=True).pack(side="left")
        else:
            label(area, "검색 결과가 없습니다.", fg=MUTED).pack(anchor="w")
        bar = ttk.Scrollbar(box, command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        tree.pack(fill="x", expand=True)
    detail = app.node_data
    if detail:
        box = card(parent, "노드 상세 및 계보")
        box.pack(fill="x", pady=(9, 0))
        result_text(frame_for_text(box), explain("node", detail), 4)
        if detail["parents"]:
            label(box, "상위 노드로 이동", size=9, fg=MUTED).pack(anchor="w")
            for sha in detail["parents"]:
                button(box, "↳  " + sha[:18] + "…", lambda p=sha: app.inspect_node(p)).pack(anchor="w")
        else:
            label(box, "계보의 시작 노드", size=9, fg=MUTED).pack(anchor="w")
    if app.catalog_data and app.catalog_data["nodes"]:
        draw_graph(app, parent, app.catalog_data["nodes"][:10])
    if app.results.get("atlas", ("", {}))[1].get("status") not in ("LOCAL_CATALOG_UNVERIFIED", "NODE_DIGEST_MATCH"):
        result(app, parent, "atlas", 3)


def frame_for_text(parent):
    row = frame(parent)
    row.pack(fill="x")
    return row


def draw_graph(app, parent, nodes):
    box = card(parent, "계보 그래프 · 조회 순서 최대 10개")
    box.pack(fill="x", pady=(9, 0))
    graph = tk.Canvas(box, bg=PANEL, height=92 if len(nodes) <= 5 else 155,
                      highlightthickness=0, takefocus=False)
    graph.pack(fill="x")
    def draw(event):
        graph.delete("all")
        count = min(len(nodes), 5)
        span = event.width / count
        points = {n["sha256"]: (int((i % 5 + .5) * span), 24 + 68 * (i // 5))
                  for i, n in enumerate(nodes)}
        for n in nodes:
            x, y = points[n["sha256"]]
            for p in n["parents"]:
                if p in points:
                    graph.create_line(*points[p], x, y, fill=TEAL, width=2, arrow="last", arrowshape=(9, 9, 4))
        for n in nodes:
            sha = n["sha256"]
            x, y = points[sha]
            graph.create_oval(x-7, y-7, x+7, y+7, fill=PRIMARY, outline=VIOLET, width=2, tags=sha)
            graph.create_text(x, y+19, text=n["node_id"][:18], fill=TEXT, font=("Consolas", 9), tags=sha)
            graph.tag_bind(sha, "<Button-1>", partial(app.inspect_node, sha))
    graph.bind("<Configure>", draw)


def player(app, parent):
    box = card(parent, "계획 검토")
    box.pack(fill="x")
    selection(box, "ProblemSpec", app.problem, lambda: app.open_problem("player"))
    selection(box, "PlanSpec", app.plan, lambda: app.choose("plan"))
    action_row(box, ("단계와 권한 확인", app.inspect_plan, True))
    if app.review:
        panel = card(parent, "예정 단계 및 영향")
        panel.pack(fill="x", pady=(9, 0))
        result_text(frame_for_text(panel), explain("plan", app.review), 5)
        row = frame(panel)
        row.pack(fill="x", pady=(6, 0))
        label(row, "중단할 단계 앞", fg=MUTED, size=9).pack(side="left")
        combo(row, app.stop_step, ["끝까지"] + [s[0] for s in app.review["steps"]], 13).pack(side="left", padx=7)
        b = button(row, "모의 실행", app.simulate, primary=True)
        b.pack(side="left")
        if (app.review["status"] != "PURE_SYNTHETIC_PREVIEW_ONLY" or
                (not (app.problem and app.plan) and
                 not (app.draft and app.library and app.review.get("plan_id")))):
            b.configure(state="disabled")
    if app.results.get("player", ("",))[0] != "plan" or not app.review:
        result(app, parent, "player", 5)


def verifier(app, parent):
    box = card(parent, "Journey 영수증")
    box.pack(fill="x")
    selection(box, "로컬 보고서", app.receipt, lambda: app.choose("receipt"))
    label(box, "파일의 SHA-256을 재계산하고, 단계·근거·결과가 영수증 계약과 일치하는지 확인합니다.",
          fg=MUTED, wrap=570).pack(fill="x", pady=4)
    action_row(box, ("무결성 검사", app.verify, True))
    own = card(parent, "사용자 목표 · 순수 실행 기록 검증")
    own.pack(fill="x", pady=(9, 0))
    label(own, "실제 Player 결과가 아닌 순수 no-op 기록만 독립 재계산합니다. 일치해도 현실 정답/독립 감사는 미확인입니다.",
          fg=AMBER, wrap=570).pack(fill="x")
    row = action_row(own, ("현재 모의 추적 재검증", app.verify_pure_trace, True))
    b = button(row, "개인 AXNODE 미검증 후보 기록", app.remember_pure_trace)
    b.pack(side="left", padx=6)
    if not app.trace_review or not app.trace_review.get("replay_integrity"):
        b.configure(state="disabled")
    result(app, parent, "verifier", 8)


def history(app, parent):
    box = card(parent, f"로컬 작업 기록   ·   {len(app.rows)} / 100")
    box.pack(fill="x")
    label(box, "최근 100건의 시각, 작업 종류, 상태를 보존합니다. 행을 선택하고 Enter를 누르면 해당 화면이 열립니다.",
          fg=MUTED, size=9, wrap=560).pack(fill="x", pady=(0, 8))
    if app.rows:
        history_table(app, box, app.rows, min(12, len(app.rows)), True)
    else:
        label(box, "아직 기록된 작업이 없습니다.", fg=MUTED).pack(anchor="w")


def settings(app, parent):
    box = card(parent, "로컬 자원 예산")
    box.pack(fill="x")
    row = frame(box)
    row.pack(fill="x")
    for i, (title, var) in enumerate(zip(("새 초안 단계 · 1–64", "새 초안 시간 · 1–300초", "설계 검색 확장 · 1–8"), app.limit_vars)):
        col = frame(row)
        col.grid(row=0, column=i, sticky="ew", padx=(0, 9))
        row.columnconfigure(i, weight=1)
        label(col, title, fg=MUTED, size=9).pack(fill="x")
        entry(col, var, width=10).pack(fill="x", ipady=4)
    action_row(box, ("예산 저장", app.set_limits, True))
    policy = card(parent, "연결 및 권한")
    policy.pack(fill="x", pady=(9, 0))
    for name, value in (("입력 파서", "CPU 규칙 사용 · Qwen 입력 파서는 CLI에서만 선택"),
                        ("Hydrogen", "OFF · 외부 송신과 자격 증명 접근은 보류"),
                        ("Player", "확인한 순수 no-op 모의 실행만 허용"),
                        ("AXNODE", "읽기 전용 · 승격, 변경, 삭제 권한 보류"),
                        ("보존 범위", "작업 기록 100건 · 확인한 메모와 저장한 초안은 로컬에 계속 보존")):
        line = frame(policy)
        line.pack(fill="x", pady=2)
        label(line, name, fg=MUTED, width=12).pack(side="left")
        label(line, value, wrap=470).pack(side="left", fill="x", expand=True)
    result(app, parent, "settings", 2)


VIEWS = dict(home=home, architect=architect, atlas=atlas, player=player, verifier=verifier,
             history=history, settings=settings)
