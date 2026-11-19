"""Run from the source root with PYTHONPATH=. and psutil in the test environment."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from time import monotonic, process_time, sleep
import json
import tkinter as tk
from tkinter import ttk
import psutil
from eai.axnode_store import AXNodeStore
from eai.desktop_app import EAIDesktopApp
from eai.desktop_bridge import DesktopBridge

def children(widget):
    for child in widget.winfo_children():
        yield child
        yield from children(child)

def button(parent, label):
    return next(w for w in children(parent) if isinstance(w, tk.Button) and w.cget("text") == label)

def controls(app):
    root = app.root
    app.select("architect")
    app.edit()
    root.update()
    top = next(w for w in children(root) if isinstance(w, tk.Toplevel))
    book = next(w for w in children(top) if isinstance(w, ttk.Notebook))
    book.select(1)
    root.update()
    box = next(w for w in children(book.nametowidget(book.select())) if isinstance(w, tk.Text))
    original = json.loads(box.get("1.0", "end-1c"))
    box.delete("1.0", "end")
    box.insert("1.0", "{")
    button(top, "초안에 적용").invoke()
    assert top.winfo_exists() and app.draft["goal"] == original["goal"]
    amended = dict(original, goal="검증용 합성 목표")
    box.delete("1.0", "end")
    box.insert("1.0", json.dumps(amended, ensure_ascii=False))
    book.select(0)
    root.update()
    button(top, "초안에 적용").invoke()
    assert app.draft["goal"] == amended["goal"]
    app.edit()
    root.update()
    top = next(w for w in children(root) if isinstance(w, tk.Toplevel))
    button(top, "닫기").invoke()
    assert app.draft["goal"] == amended["goal"]

def run():
    proc = psutil.Process()
    metrics = {}
    with TemporaryDirectory() as tmp:
        root = tk.Tk()
        root.geometry("1080x650")
        app = EAIDesktopApp(root, DesktopBridge(Path(tmp)/"한글 검증"))
        def measure(name, action):
            start = monotonic()
            cpu = process_time()
            first_rss = proc.memory_info().rss
            peak = first_rss
            ticks = []
            previous = start
            action()
            while app.busy:
                root.update()
                now = monotonic()
                ticks.append(now-previous)
                previous = now
                peak = max(peak, proc.memory_info().rss)
                if now-start > 45:
                    raise TimeoutError(name)
                sleep(.004)
            root.update()
            metrics[name] = dict(wall_ms=round(1000*(monotonic()-start)), cpu_ms=round(1000*(process_time()-cpu)), peak_sampled_rss_mib=round(peak/1048576,1), max_event_pump_gap_ms=round(1000*max(ticks, default=0)), pumps=len(ticks))
        try:
            measure("startup_source", lambda: None)
            app.fill_command("계산: 12 * (3 + 4)")
            measure("command", app.ask)
            assert "84" in app.results["home"][1]["text"]
            measure("practice", app.practice)
            measure("architect", app.design)
            assert len(app.results["architect"][1]["alternatives"]) == 2
            app.select("player")
            measure("inspect_plan", app.inspect_plan)
            with patch("eai.desktop_app.messagebox.askyesno", return_value=True):
                measure("pure_simulation", app.simulate)
            assert app.results["player"][1]["external_actions"] == 0
            app.select("verifier")
            measure("verify", app.verify)
            assert "DIGEST_INTEGRITY" in app.results["verifier"][1]["status"]
            with AXNodeStore(app.example.library) as store:
                specimen = store.get(store.hashes()[0]).as_dict()
                for idx in range(240):
                    specimen["id"] = f"fixture.item{idx:03}"
                    store.import_node(json.dumps(specimen))
            app.select("atlas")
            with patch("eai.desktop_app.filedialog.askdirectory", return_value=str(app.example.library)):
                measure("catalog_243", app.choose_library)
            assert (app.catalog_data["total_nodes"], app.catalog_data["shown"], app.catalog_data["truncated"]) == (243,200,True)
            for field, path in (("plan", app.example.plan), ("receipt", app.example.receipt)):
                with patch("eai.desktop_app.filedialog.askopenfilename", return_value=str(path)):
                    app.choose(field)
                with patch("eai.desktop_app.filedialog.askopenfilename", return_value=""):
                    app.choose(field)
                assert getattr(app, field) == path
            controls(app)
            measure("save_new_draft", app.save)
            assert app.bridge.load_draft(app.problem)["goal"] == "검증용 합성 목표"
            app.select("settings")
            app.limit_vars[0].set("999")
            app.set_limits()
            assert app.bridge.state.limits().steps == 8
            app.select("history")
            tree = next(w for w in children(root) if isinstance(w, ttk.Treeview))
            tree.selection_set(tree.get_children()[0])
            tree.focus_force()
            root.update()
            tree.event_generate("<Return>")
            root.update()
            assert app.page == "architect"
        finally:
            app.close()
    print(json.dumps(dict(status="PASS", verified_nodes=243, displayed_nodes=200, metrics=metrics), indent=2))

if __name__ == "__main__":
    run()
