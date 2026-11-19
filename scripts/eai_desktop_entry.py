"""Frozen native GUI entry and explicit offline, source-aware package self-check.

The check deliberately does not instantiate a Tk window, open user data, access
credentials, create the private EAI root, or make network connections. A frozen
unsigned EXE writes a report only to a NEW explicitly chosen local path.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import sys
import tkinter

from eai.desktop_app import main

_REQUIRED_MODULES = (
    "eai.desktop_app", "eai.desktop_bridge", "eai.desktop_state",
    "eai.architect_runtime", "eai.axnode_store", "eai.axnode_memory_review",
    "eai.policy_gate", "eai.player_runtime", "eai.desktop_views",
    "eai.desktop_presentation",
)
_BUNDLED_NOTICES = (
    "notices/python/LICENSE.txt", "notices/tcl/tcl-license.terms",
    "notices/tk/license.terms",
)


def self_check(report_path: str) -> int:
    """Validate offline imports and bundled notice inventory; never execute EAI."""
    from eai.local_files import local_path
    from eai.desktop_bridge import DesktopBridge
    from eai.contracts import ProblemSpec

    target = local_path(report_path, private=True)
    if target.suffix.lower() != ".json" or not target.parent.is_dir() or target.exists():
        raise ValueError("new JSON report path in an existing local folder required")
    if target.is_symlink():
        raise ValueError("report path cannot be linked")
    loaded = []
    for module in _REQUIRED_MODULES:
        importlib.import_module(module)
        loaded.append(module)
    sample = DesktopBridge.make_problem_draft("offline-only entry self-check")
    ProblemSpec.validate(sample)
    frozen = bool(getattr(sys, "frozen", False))
    base = Path(getattr(sys, "_MEIPASS", "")) if frozen else None
    licenses = {item: bool(base and (base / item).is_file()) for item in _BUNDLED_NOTICES}
    ok = not frozen or (sys.version_info[:2] == (3, 11) and all(licenses.values()))
    report = {
        "schema": "eai.desktop.v32.selfcheck.v1",
        "status": "PASS_UNSIGNED_BUNDLE_IMPORTS" if frozen and ok else
                  "PASS_SOURCE_IMPORTS_ONLY" if ok else "FAIL_BUNDLE_PREREQUISITE",
        "mode": "FROZEN_UNSIGNED" if frozen else "SOURCE_ONLY",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "tk": str(tkinter.TkVersion), "modules": loaded,
        "license_inventory": licenses if frozen else "NOT_APPLICABLE_SOURCE_ONLY",
        "network": "NOT_ATTEMPTED", "real_player": "NOT_RUN",
        "native_gui_e2e": "NOT_RUN", "independent_audit": "NOT_RUN",
        "original_writes": 0, "external_actions": 0,
    }
    content = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with target.open("x", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return 0 if ok else 2


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(main())
    if len(args) == 3 and args[:2] == ["--self-check", "--report"]:
        try:
            raise SystemExit(self_check(args[2]))
        except (ValueError, OSError, ImportError):
            # This is a GUI EXE without a console: leave no misleading PASS.
            raise SystemExit(2)
    raise SystemExit(64)
