"""Local-only native EAI UI bridge. No shell, cloud dispatch, or approval minting."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from .contracts import MAX_DOCUMENT_BYTES, ProblemSpec, strict_json
from .intent import RuleIntentParser

_SAFE_SHA = re.compile(r"[0-9a-f]{64}\Z")


def private_root() -> Path:
    """Separate desktop state from the legacy EAI database and AXNODE store."""
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "EAI" / "Desktop"
    return Path.home() / ".eai" / "desktop"


def _existing_file(path: str | Path, limit: int = MAX_DOCUMENT_BYTES) -> Path:
    p = Path(path).expanduser()
    if not p.is_file() or p.is_symlink() or p.stat().st_size > limit:
        raise ValueError("explicit bounded ordinary local file required")
    return p


def _existing_store(root: str | Path) -> Path:
    p = Path(root).expanduser()
    if (not p.is_dir() or p.is_symlink() or (p / "axnodes.sqlite").is_symlink()
            or (p / "nodes").is_symlink() or not (p / "nodes").is_dir()
            or not (p / "axnodes.sqlite").is_file()):
        raise ValueError("an existing AXNODE catalog must be selected")
    return p


class DesktopBridge:
    """Explicit, bounded in-process routes into existing EAI contracts."""

    def __init__(self, state_root: str | Path | None = None):
        self.state_root = Path(state_root) if state_root is not None else private_root()
        self.rule_parser = RuleIntentParser()

    def ask(self, question: str, *, consent_to_note: bool = False) -> dict[str, Any]:
        if type(question) is not str or not 1 <= len(question.strip()) <= 4000:
            raise ValueError("command must contain 1..4000 characters")
        intent = self.rule_parser.parse(question)
        if intent.task == "unsupported":
            return {"kind": "COMMAND", "status": "HOLD_UNSUPPORTED_REQUEST",
                    "text": "일반 명령으로 실행할 수 없습니다. '설계 초안'을 만들거나 계산/비교/도움말 명령을 사용하세요.",
                    "requires_approval": False, "external_calls": 0}
        if intent.task == "remember" and not consent_to_note:
            return {"kind": "COMMAND", "status": "HOLD_EXPLICIT_NOTE_APPROVAL",
                    "text": "로컬 메모 저장은 별도 확인 후에만 수행합니다.",
                    "requires_approval": True, "external_calls": 0}
        if intent.task == "search":
            return {"kind": "COMMAND", "status": "HOLD_NO_REMOTE_OR_LOCAL_SEARCH_CONFIGURED",
                    "text": "데스크톱의 온라인 검색은 비활성화되어 있습니다.",
                    "requires_approval": False, "external_calls": 0}
        from .runner import EAIRunner
        from .storage import Store
        # Construct only after explicit user command. Never use EAI_DB or old DB.
        self.state_root.mkdir(parents=True, exist_ok=True)
        if self.state_root.is_symlink():
            raise ValueError("desktop state cannot be a symlink")
        db_path = self.state_root / "desktop_history.sqlite3"
        if db_path.is_symlink():
            raise ValueError("desktop state file cannot be a symlink")
        store = Store(db_path)
        try:
            answer = EAIRunner(store).ask(question, allow_online=False)
        finally:
            store.close()
        return {"kind": "COMMAND", "status": answer.result.status,
                "text": answer.text[:12000], "requires_approval": False,
                "external_calls": 0, "authority": "LOCAL_CPU_ONLY"}

    @staticmethod
    def make_problem_draft(goal: str, *, domain: str = "general",
                           risk: str = "MEDIUM", max_steps: int = 8,
                           max_seconds: int = 60) -> dict:
        """Unverified editable draft, not a claim to understand arbitrary speech."""
        if type(goal) is not str or not 1 <= len(goal.strip()) <= 2000:
            raise ValueError("goal must contain 1..2000 characters")
        raw = {"version": 1, "id": "draft_" + uuid4().hex[:16],
               "goal": goal.strip(), "domain": domain,
               "state_refs": [], "assumptions": [], "hard_constraints": [],
               "objectives": [], "oracle": "owner_review_required",
               "permissions": ["pure"],
               "budget": {"max_steps": max_steps, "max_seconds": max_seconds},
               "risk": risk}
        ProblemSpec.validate(raw)
        return raw

    def save_new_draft(self, raw: dict) -> Path:
        """Only save new, user-reviewed private files; no overwrite or old DB."""
        ProblemSpec.validate(raw)
        body = json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        if len(body) > MAX_DOCUMENT_BYTES:
            raise ValueError("draft exceeds maximum size")
        self.state_root.mkdir(parents=True, exist_ok=True)
        if self.state_root.is_symlink():
            raise ValueError("desktop state cannot be a symlink")
        draft_dir = self.state_root / "drafts"
        if draft_dir.is_symlink():
            raise ValueError("draft directory cannot be a symlink")
        draft_dir.mkdir(exist_ok=True)
        target = draft_dir / (raw["id"] + ".json")
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target

    @staticmethod
    def architect(problem_file: str | Path, axnode_root: str | Path) -> dict:
        from .architect_runtime import preview_architecture
        from .trace_renderer import render_architect_explanation
        _existing_file(problem_file)
        _existing_store(axnode_root)
        report = preview_architecture(problem_file, axnode_root)
        return render_architect_explanation(report)

    @staticmethod
    def player(problem_file: str | Path, plan_file: str | Path,
               *, acknowledged_pure_only: bool = False) -> dict:
        if acknowledged_pure_only is not True:
            return {"kind": "PLAYER", "status": "HOLD_PURE_SIMULATION_CONFIRMATION",
                    "execution": "NOT_EXECUTED", "real_world_verified": False}
        from .player_cli import player_preview
        from .trace_renderer import render_player_explanation
        _existing_file(problem_file)
        _existing_file(plan_file)
        return render_player_explanation(player_preview(problem_file, plan_file))

    @staticmethod
    def verify_journey(report_file: str | Path) -> dict:
        from .offline_journey import audit_offline_journey_report
        from .contracts import strict_json
        raw = strict_json(_existing_file(report_file).read_bytes())
        return audit_offline_journey_report(raw)

    @staticmethod
    def axnode_catalog(root: str | Path, *, query: str = "") -> dict:
        """Read-only SQLite inventory; never initializes a new node store/index."""
        if type(query) is not str or len(query) > 120 or "\x00" in query:
            raise ValueError("invalid local AXNODE filter")
        path = _existing_store(root) / "axnodes.sqlite"
        # mode=ro keeps this viewer from migrating, indexing or editing the DB.
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=2) as db:
            db.execute("PRAGMA query_only=ON")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version != 1:
                raise ValueError("unknown AXNODE schema version")
            cols = {row[1] for row in db.execute("PRAGMA table_info(nodes)")}
            if cols != {"sha256", "node_id", "version", "status", "kind", "output_type", "search_text"}:
                raise ValueError("unexpected AXNODE catalog columns")
            rows = db.execute(
                "SELECT sha256,node_id,version,status,kind,output_type FROM nodes "
                "WHERE search_text LIKE ? ESCAPE '!' ORDER BY node_id,version LIMIT 200",
                ("%" + query.replace("!", "!!").replace("%", "!%")
                 .replace("_", "!_") + "%",)).fetchall()
            count = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            digests = [row[0] for row in rows]
            if any(type(s) is not str or not _SAFE_SHA.fullmatch(s) for s in digests):
                raise ValueError("untrusted node digest")
            parents = {}
            for sha in digests:
                parents[sha] = [row[0] for row in db.execute(
                    "SELECT parent_sha FROM parents WHERE child_sha=? ORDER BY parent_sha LIMIT 32",
                    (sha,))]
            if any(type(p) is not str or not _SAFE_SHA.fullmatch(p)
                   for values in parents.values() for p in values):
                raise ValueError("untrusted parent digest")
        return {"kind": "AXNODE", "status": "LOCAL_CATALOG_UNVERIFIED",
                "total_nodes": count, "shown": len(rows), "truncated": count > 200,
                "nodes": [dict(sha256=s, node_id=n, version=v, status=state,
                               kind=k, output_type=o, parents=parents[s])
                          for s,n,v,state,k,o in rows], "external_calls": 0}
