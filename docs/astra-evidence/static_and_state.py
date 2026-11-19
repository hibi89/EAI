"""Defensive audit of desktop entry points and the isolated synthetic acceptance profile."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import ast
import importlib
import json
import os
import pkgutil
import sqlite3
import sys
import eai

def inspect_desktop(repo):
    files = sorted((repo / "eai").glob("desktop_*.py")) + [repo / "scripts" / "eai_desktop_entry.py"]
    forbidden = {"eval", "exec", "compile", "__import__", "os.system", "os.popen", "subprocess.run",
                 "subprocess.call", "subprocess.Popen", "socket.create_connection", "urllib.request.urlopen",
                 "requests.post", "win32cred.CredRead"}
    findings = []
    for f in files:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in forbidden:
                findings.append((f.name, node.lineno))
    assert not findings, findings
    with patch("socket.socket.connect", side_effect=AssertionError("network during import")):
        mods = list(pkgutil.walk_packages(eai.__path__, eai.__name__ + "."))
        for m in mods:
            importlib.import_module(m.name)
    return {"direct_sensitive_call_sites":len(findings), "desktop_files":len(files), "module_imports":len(mods)}

def inspect_profile(path):
    path = path.resolve(strict=True)
    def db(name):
        return sqlite3.connect((path / name).as_uri()+"?mode=ro",uri=True)
    with closing(db("workspace.sqlite3")) as c:
        assert c.execute("pragma integrity_check").fetchone() == ("ok",)
        states=c.execute("select page,op,status from events order by id").fetchall()
        assert ("home","command","OK") in states
        fields=[r[1] for r in c.execute("pragma table_info(events)")]
    with closing(db("desktop_history.sqlite3")) as c:
        assert c.execute("pragma integrity_check").fetchone() == ("ok",)
        turns=c.execute("select count(*) from turns").fetchone()[0]
        assert turns==0
    return {"synthetic_journal_rows":len(states),"event_schema":fields,"raw_turn_count":turns,"integrity":"ok"}

if __name__=="__main__":
    repo=Path.cwd()
    result=inspect_desktop(repo)
    if len(sys.argv)>1:
        result.update(inspect_profile(Path(sys.argv[1])))
    print(json.dumps(result,indent=2))
