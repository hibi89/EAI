"""Typed, local-only routes from the native workstation to the EAI engine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from .axnode_schema import HASH, NAME
from .axnode_store import AXNodeStore
from .contracts import MAX_DOCUMENT_BYTES, PlanSpec, ProblemSpec, canonical_sha256, strict_json
from .desktop_state import DesktopState, private_db
from .intent import RuleIntentParser
from .local_files import local_path, read_bytes


def private_root() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "EAI" / "Desktop"
    return Path.home() / ".eai" / "desktop"


def _document(path: str | Path) -> dict:
    return strict_json(read_bytes(path, MAX_DOCUMENT_BYTES))


def _sha(value):
    if type(value) is not str or not HASH.fullmatch(value):
        raise ValueError("invalid catalog digest")
    return value


def _identifier(value):
    if type(value) is not str or not NAME.fullmatch(value):
        raise ValueError("invalid catalog identifier")
    return value


class DesktopBridge:
    def __init__(self, state_root: str | Path | None = None):
        self.state_root = Path(state_root) if state_root is not None else private_root()
        self.state = DesktopState(self.state_root)
        self.rule_parser = RuleIntentParser()

    def ask(self, question: str, *, consent_to_note: bool = False) -> dict:
        if type(question) is not str or len(question) > 4000 or "\x00" in question:
            raise ValueError("invalid command")
        intent = self.rule_parser.parse(question)
        base = {"kind": "COMMAND", "requires_approval": False, "external_calls": 0}
        if intent.task == "unsupported":
            return dict(base, status="HOLD_UNSUPPORTED_REQUEST",
                        text="이 요청을 실행할 규칙이 없습니다. 설계 초안으로 열어 목표와 조건을 정할 수 있습니다.")
        if intent.task == "remember" and consent_to_note is not True:
            return dict(base, status="HOLD_EXPLICIT_NOTE_APPROVAL", requires_approval=True,
                        text="메모를 로컬에 남기려면 저장을 확인해 주세요.")
        if intent.task == "search":
            return dict(base, status="HOLD_NO_REMOTE_OR_LOCAL_SEARCH_CONFIGURED",
                        text="데스크톱에서 외부 검색은 꺼져 있습니다. 저장한 메모는 ‘기억검색’으로 찾을 수 있습니다.")
        from .runner import EAIRunner
        from .storage import Store
        store = Store(private_db(self.state_root, "desktop_history.sqlite3"))
        try:
            answer = EAIRunner(store).ask(question, allow_online=False, persist_turns=False)
        finally:
            store.close()
        return dict(base, status=answer.result.status, text=answer.text[:12000],
                    task=intent.task, authority="LOCAL_CPU_ONLY")

    @staticmethod
    def make_problem_draft(goal: str, *, domain: str = "general", risk: str = "MEDIUM",
                           max_steps: int = 8, max_seconds: int = 60) -> dict:
        if type(goal) is not str:
            raise ValueError("text goal required")
        raw = {"version": 1, "id": "draft_" + uuid4().hex[:16], "goal": goal.strip(),
               "domain": domain, "state_refs": [], "assumptions": [], "hard_constraints": [],
               "objectives": [], "oracle": "owner_review_required", "permissions": ["pure"],
               "budget": {"max_steps": max_steps, "max_seconds": max_seconds}, "risk": risk}
        ProblemSpec.validate(raw)
        return raw

    @staticmethod
    def load_draft(path: str | Path) -> dict:
        raw = _document(path)
        ProblemSpec.validate(raw)
        return raw

    def save_new_draft(self, raw: dict) -> Path:
        ProblemSpec.validate(raw)
        body = json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        if len(body) > MAX_DOCUMENT_BYTES:
            raise ValueError("draft exceeds maximum size")
        folder = local_path(self.state_root / "drafts", private=True)
        folder.mkdir(parents=True, exist_ok=True)
        target = local_path(folder / (raw["id"] + ".json"), private=True)
        fd, staging = tempfile.mkstemp(dir=folder, prefix=".draft-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(staging, target)
        finally:
            Path(staging).unlink(missing_ok=True)
        return target

    @staticmethod
    def architect(problem_file, axnode_root, *, max_expansions=8, cancelled=None) -> dict:
        from .architect_runtime import preview_architecture
        from .trace_renderer import render_architect_explanation
        report = preview_architecture(problem_file, axnode_root, max_expansions=max_expansions,
                                      cancelled=cancelled)
        result = render_architect_explanation(report)
        result["expansions"] = report["plan_search_expansions"]
        problem = ProblemSpec.validate(_document(problem_file))
        if problem.digest() != result["problem_sha256"]:
            raise ValueError("problem changed during design")
        plans = {}
        for choice in report["advisory_plans"]:
            raw = {"version": 1, "problem_sha256": problem.digest(), "steps": choice["plan_steps"],
                   "budget": {"max_steps": problem.budget[0], "max_seconds": problem.budget[1]}}
            PlanSpec.validate(raw)
            plans[choice["alternative_id"]] = raw
        result["plan_specs"] = plans
        return result

    @staticmethod
    def journey_receipt(problem_file, axnode_root, *, max_expansions, expected_problem):
        from .offline_journey import audit_offline_journey_report, preview_offline_journey
        report = preview_offline_journey(problem_file, axnode_root, max_expansions=max_expansions)
        if report["problem_sha256"] != expected_problem:
            raise ValueError("changed problem requires new review")
        audit_offline_journey_report(report)
        return report

    @staticmethod
    def inspect_plan(problem_file, plan_file) -> dict:
        from .policy_gate import evaluate_plan_policy
        problem = ProblemSpec.validate(_document(problem_file))
        plan = PlanSpec.validate(_document(plan_file))
        policy = evaluate_plan_policy(problem, plan)
        return {"status": policy.disposition, "problem_sha256": problem.digest(),
                "plan_sha256": policy.plan_sha256, "reasons": policy.reason_codes,
                "steps": plan.steps, "budget": plan.budget, "risk": problem.risk,
                "permissions": problem.permissions}

    @staticmethod
    def player(problem_file, plan_file, *, acknowledged_pure_only=False,
               reviewed_digests=None, cancel_before_step=None) -> dict:
        if acknowledged_pure_only is not True:
            return {"kind": "PLAYER", "status": "HOLD_PURE_SIMULATION_CONFIRMATION",
                    "execution": "NOT_EXECUTED", "real_world_verified": False}
        from .policy_gate import plan_digest
        from .player_runtime import run_bounded_pure_player
        problem = ProblemSpec.validate(_document(problem_file))
        plan = PlanSpec.validate(_document(plan_file))
        if reviewed_digests is not None and reviewed_digests != (problem.digest(), plan_digest(plan)):
            return {"kind": "PLAYER", "status": "HOLD_PLAN_CHANGED", "execution": "NOT_EXECUTED"}
        observed = run_bounded_pure_player(problem, plan, interpret_pure_noop=True,
                                           cancel_before_step=cancel_before_step)
        return {"kind": "PLAYER", "status": observed.status, "plan_sha256": observed.plan_sha256,
                "problem_sha256": observed.problem_sha256, "trace_sha256": observed.trace_sha256,
                "interpreted_steps": observed.interpreted_steps, "replay": observed.replay_status,
                "reasons": observed.reason_codes, "original_writes": observed.original_writes,
                "external_actions": observed.external_actions, "verified_real_world": False,
                "execution": "DENIED" if observed.reason_codes else "PURE_SYNTHETIC_NOOP_ONLY"}

    @staticmethod
    def verify_journey(report_file) -> dict:
        from .offline_journey import audit_offline_journey_report
        raw = _document(report_file)
        claimed = raw.get("receipt_sha256")
        digest = canonical_sha256({k: v for k, v in raw.items() if k != "receipt_sha256"})
        base = {"calculated_sha256": digest, "receipt_sha256": None,
                "independent_verification": "NOT_ESTABLISHED"}
        if type(claimed) is not str or not HASH.fullmatch(claimed):
            return dict(base, status="RECEIPT_CONTRACT_REJECTED")
        base["receipt_sha256"] = claimed
        if claimed != digest:
            return dict(base, status="RECEIPT_DIGEST_MISMATCH")
        try:
            audit = audit_offline_journey_report(raw)
        except (ValueError, KeyError, TypeError):
            return dict(base, status="RECEIPT_CONTRACT_REJECTED")
        return dict(audit, calculated_sha256=digest, truth_status=raw["truth_status"],
                    evidence_review_required=raw["evidence_review_required"],
                    conflict_count=raw["contradiction_count"], unknown_count=raw["unknown_count"],
                    problem_sha256=raw["problem_sha256"])

    @staticmethod
    def axnode_catalog(root, *, query="", status="") -> dict:
        if (type(query) is not str or len(query) > 120 or "\x00" in query or
                status not in ("", "CANDIDATE", "DRAFT")):
            raise ValueError("invalid catalog filter")
        with AXNodeStore(root, read_only=True) as store:
            needle = "%" + query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            rows = store.db.execute(
                "SELECT sha256,node_id,version,status,kind,output_type FROM nodes "
                "WHERE search_text LIKE ? ESCAPE '!' AND (?='' OR status=?) "
                "ORDER BY node_id,version LIMIT 201", (needle, status, status)).fetchall()
            total = store.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            nodes = []
            for sha, name, version, state, kind, output in rows[:200]:
                if (state not in ("CANDIDATE", "DRAFT") or type(version) is not int
                        or not 1 <= version <= 2147483647):
                    raise ValueError("invalid catalog metadata")
                parents = [_sha(p) for p, in store.db.execute(
                    "SELECT parent_sha FROM parents WHERE child_sha=? ORDER BY parent_sha LIMIT 13", (sha,))]
                if len(parents) > 12:
                    raise ValueError("unbounded lineage")
                nodes.append(dict(sha256=_sha(sha), node_id=_identifier(name), version=version,
                                  status=state, kind=_identifier(kind), output_type=_identifier(output),
                                  parents=parents))
        return {"kind": "AXNODE", "status": "LOCAL_CATALOG_UNVERIFIED", "total_nodes": total,
                "shown": len(nodes), "truncated": len(rows) > 200, "nodes": nodes, "external_calls": 0}

    @staticmethod
    def node_detail(root, sha: str) -> dict:
        with AXNodeStore(root, read_only=True) as store:
            raw = store.get(_sha(sha)).as_dict()
            return {"status": "NODE_DIGEST_MATCH", "sha256": sha, "node_id": raw["id"],
                    "version": raw["version"], "node_status": raw["status"],
                    "source": raw["provenance"]["source"], "author": raw["provenance"]["author"],
                    "parents": tuple(sorted(raw["parent_hashes"])), "output": raw["signature"]["output"]}
