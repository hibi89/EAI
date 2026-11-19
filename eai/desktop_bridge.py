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
    def draft_review(raw: dict) -> dict:
        """Bounded missing-evidence report; not evidence discovery or truth validation."""
        problem = ProblemSpec.validate(raw)
        missing = []
        if not problem.state_refs:
            missing.append("NO_EVIDENCE_REFS")
        if not problem.objectives:
            missing.append("NO_OBJECTIVES")
        if problem.oracle == "owner_review_required":
            missing.append("ORACLE_NOT_DEFINED")
        if not problem.hard_constraints:
            missing.append("NO_EXPLICIT_CONSTRAINTS")
        return {"kind": "PROBLEM_DRAFT_REVIEW", "status": "REVIEW_REQUIRED" if missing else "FORM_COMPLETE_UNVERIFIED",
                "missing": missing, "permission_scope": list(problem.permissions),
                "assumption_count": len(problem.assumptions),
                "evidence_ref_count": len(problem.state_refs),
                "objective_count": len(problem.objectives),
                "problem_sha256": problem.digest(),
                "truth_verified": False, "external_actions": 0}

    def create_fresh_private_library(self, *, owner_approved: bool = False) -> dict:
        """Create only a new EAI-private empty AXNODE library, never touch old data."""
        if owner_approved is not True:
            return {"status": "HOLD_PRIVATE_LIBRARY_CONSENT", "created": False}
        root = local_path(self.state_root, private=True)
        if not root.is_dir():
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder = local_path(root / "libraries", private=True)
        folder.mkdir(mode=0o700, exist_ok=True)
        for _ in range(4):
            target = local_path(folder / ("library_" + uuid4().hex[:16]), private=True)
            try:
                target.mkdir(mode=0o700)
                break
            except FileExistsError:
                continue
        else:
            raise FileExistsError("no unique library path available")
        with AXNodeStore(target) as library:
            if library.db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("new private library integrity failure")
        return {"status": "PRIVATE_EMPTY_LIBRARY_CREATED", "created": True,
                "path": target, "node_count": 0, "original_writes": 0,
                "external_actions": 0}

    def import_private_candidate(self, library_root: str | Path, source_path: str | Path,
                                 *, owner_approved: bool = False) -> dict:
        """Copy one owner-reviewed bounded AXNODE into a new *private* candidate index."""
        if owner_approved is not True:
            return {"status": "HOLD_PRIVATE_IMPORT_CONSENT", "imported": False}
        private_libraries = local_path(self.state_root / "libraries", private=True)
        selected = local_path(library_root, private=True)
        if selected.parent != private_libraries or not selected.name.startswith("library_"):
            raise ValueError("only new EAI-private libraries accept imports")
        from .axnode_schema import MAX_NODE_BYTES
        payload = read_bytes(source_path, MAX_NODE_BYTES)
        with AXNodeStore(selected) as store:
            digest = store.import_node(payload)
            total = store.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        return {"status": "PRIVATE_CANDIDATE_IMPORTED_UNVERIFIED", "imported": True,
                "sha256": digest, "node_count": total,
                "original_writes": 0, "external_actions": 0,
                "authority": "DRAFT_OR_CANDIDATE_ONLY_NO_ACTIVE"}

    @staticmethod
    def discover_goal_capabilities(raw: dict, axnode_root: str | Path | None = None) -> dict:
        """Discover real pre-registered typed CPU kinds and chosen local AXNODE hints.

        A string description is NOT parsed as a verified typed goal or executable plan.
        No default library, model, network, action handler or original-data scan.
        """
        problem = ProblemSpec.validate(raw)
        from .goal_dispatch import ROUTED_KINDS, ROUTER_VERSION
        from .axnode_retrieval import AXNodeRetriever
        matched = problem.domain if problem.domain in ROUTED_KINDS else None
        candidates = []
        library_status = "NO_LIBRARY_SELECTED"
        if axnode_root is not None:
            if "local.read" not in problem.permissions:
                library_status = "HOLD_LOCAL_READ_NOT_APPROVED"
            else:
                with AXNodeStore(axnode_root, read_only=True) as store:
                    candidates = [
                        {"sha256": node.sha256, "node_id": node.node_id,
                         "status": node.status, "output_type": node.output_type,
                         "score": node.score, "provenance": node.provenance}
                        for node in AXNodeRetriever(store).find(problem.goal[:300], limit=8)
                    ]
                library_status = "LOCAL_HINTS_UNVERIFIED" if candidates else "NO_MATCHING_LOCAL_NODES"
        return {
            "kind": "GOAL_CAPABILITY_DISCOVERY",
            "status": "TYPED_DOMAIN_MATCH_UNVERIFIED" if matched else "NO_TYPED_CPU_MATCH",
            "matched_typed_domain": matched,
            "available_typed_domains": sorted(ROUTED_KINDS),
            "route_registry": ROUTER_VERSION,
            "library_status": library_status,
            "node_candidates": candidates,
            "problem_sha256": problem.digest(),
            "execution": "NOT_EXECUTED",
            "plan_verified": False, "real_world_verified": False,
            "external_actions": 0,
            "next_step": "REVIEW_TYPED_INPUTS_AND_LOCAL_EVIDENCE" if matched or candidates
                         else "OWNER_MUST_SELECT_SUPPORTED_DOMAIN_OR_PROVIDE_LOCAL_EVIDENCE",
        }

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
    def architect_reviewed_goal(raw: dict, axnode_root: str | Path | None, *,
                                owner_reviewed: bool = False,
                                max_expansions: int = 8, cancelled=None) -> dict:
        """Explicitly reviewed goal -> real, hash-pinned Architect alternatives.

        A review is consent to *read the selected library*, never to execute
        Player, use cloud, save an original or mark semantic evidence verified.
        """
        problem = ProblemSpec.validate(raw)
        digest = problem.digest()
        base = {"kind": "REVIEWED_GOAL_ARCHITECT", "problem_sha256": digest,
                "execution": "NOT_EXECUTED", "model": "LOCAL_CPU_ONLY",
                "independent_verification": "NOT_ESTABLISHED", "can_execute": False,
                "plan_specs": {}, "alternatives": [], "external_actions": 0}
        if owner_reviewed is not True:
            return dict(base, status="HOLD_OWNER_REVIEW_REQUIRED",
                        blockers=["OWNER_REVIEW_NOT_CONFIRMED"])
        review = DesktopBridge.draft_review(raw)
        if review["status"] != "FORM_COMPLETE_UNVERIFIED":
            return dict(base, status="HOLD_INCOMPLETE_PROBLEM",
                        blockers=review["missing"])
        if "local.read" not in problem.permissions:
            return dict(base, status="HOLD_LOCAL_READ_NOT_APPROVED",
                        blockers=["LOCAL_READ_PERMISSION_REQUIRED"])
        if axnode_root is None:
            return dict(base, status="HOLD_LOCAL_LIBRARY_REQUIRED",
                        blockers=["EXPLICIT_AXNODE_LIBRARY_REQUIRED"])
        from .architect_runtime import preview_architecture_problem
        from .trace_renderer import render_architect_explanation
        report = preview_architecture_problem(problem, axnode_root,
                                              max_expansions=max_expansions,
                                              cancelled=cancelled)
        result = render_architect_explanation(report)
        if result["problem_sha256"] != digest:
            raise ValueError("cross-goal Architect response")
        sources = []
        plans = {}
        for choice in report["advisory_plans"]:
            candidate = {"version": 1, "problem_sha256": digest,
                         "steps": choice["plan_steps"],
                         "budget": {"max_steps": problem.budget[0],
                                    "max_seconds": problem.budget[1]}}
            PlanSpec.validate(candidate)
            plans[choice["alternative_id"]] = candidate
            sources.append(tuple(choice["node_hashes"]))
        # One valid branch does not demonstrate a genuine two-way decision.
        if (report["status"] != "CANDIDATES_UNVERIFIED"
                or len(plans) != 2 or len(set(sources)) != 2):
            return dict(base, status="HOLD_DISTINCT_PLANS_NOT_ESTABLISHED",
                        engine_status=report["status"],
                        blockers=([report["design_blocked_reason"]] if
                                  report["design_blocked_reason"] else []) +
                                 [item["reason"] for item in report["blocked_alternatives"]] +
                                 (["TWO_DISTINCT_BOUNDED_PLANS_REQUIRED"] if len(plans) != 2 else []),
                        unknown_count=len(report["analysis"]["unknowns"]),
                        expansions=report["plan_search_expansions"])
        compare = []
        obligations = {item["alternative_id"]: item
                       for item in report["option_obligations"]}
        for item in report["advisory_plans"]:
            obligation = obligations[item["alternative_id"]]
            operators = [step["operator"] for step in item["plan_steps"]]
            compare.append({
                "id": item["alternative_id"],
                "strategy_refs": list(obligation["strategy_refs"]),
                "evidence_hashes": list(item["node_hashes"]),
                "tradeoffs": list(obligation["tradeoffs"]),
                "verification_required": obligation["verification_required"],
                "declared_steps": item["declared_step_count"],
                "declared_seconds_upper_bound": item["declared_seconds_upper_bound"],
                "operators": operators,
                "reversibility": ("PURE_NOOP_NO_CHANGES" if
                                  set(operators) == {"synthetic.noop.v1"} else
                                  "NOT_ESTABLISHED_NON_PURE_BLOCKED"),
                "source_status": "LOCAL_CANDIDATE_UNVERIFIED",
                "independent_accuracy": "UNKNOWN",
            })
        return dict(base, status="TWO_PLANS_ADVISORY_UNVERIFIED",
                    comparison=compare,
                    engine_status=report["status"],
                    truth_status=report["truth_status"],
                    plan_specs=plans, alternatives=result["alternatives"],
                    uncertainty=result["uncertainty"],
                    evidence_review_required=report["evidence_review_required"],
                    source_sets=[list(hashes) for hashes in sources],
                    expansions=report["plan_search_expansions"],
                    blockers=[item["reason"] for item in report["blocked_alternatives"]])

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
    def inspect_reviewed_selection(problem_raw: dict, design: dict, selected_id: str,
                                   axnode_root: str | Path | None) -> dict:
        """Fail-closed selection: recompute the actual library/plan before policy review.

        Any UI/tool mutation between Architect and Player invalidates the
        selection. Pure simulation still requires a separate later confirmation.
        """
        problem = ProblemSpec.validate(problem_raw)
        digest = problem.digest()
        base = {"kind": "REVIEWED_PLAN_POLICY", "problem_sha256": digest,
                "status": "HOLD_PLAN_CHANGED", "execution": "NOT_EXECUTED",
                "original_writes": 0, "external_actions": 0,
                "independent_verification": "NOT_ESTABLISHED",
                "can_execute_real_actions": False}
        if (type(design) is not dict or
                design.get("kind") != "REVIEWED_GOAL_ARCHITECT" or
                design.get("status") != "TWO_PLANS_ADVISORY_UNVERIFIED" or
                design.get("problem_sha256") != digest or
                type(selected_id) is not str or
                type(design.get("plan_specs")) is not dict or
                selected_id not in design["plan_specs"]):
            return dict(base, reasons=["STALE_OR_UNREVIEWED_DESIGN"])
        if axnode_root is None or "local.read" not in problem.permissions:
            return dict(base, reasons=["LOCAL_SOURCE_READ_NOT_AUTHORIZED"])
        # Re-read every candidate hash/contract from the *selected* library.
        fresh = DesktopBridge.architect_reviewed_goal(
            problem_raw, axnode_root, owner_reviewed=True)
        if (fresh.get("status") != "TWO_PLANS_ADVISORY_UNVERIFIED" or
                fresh.get("plan_specs") != design.get("plan_specs") or
                fresh.get("source_sets") != design.get("source_sets") or
                fresh.get("alternatives") != design.get("alternatives")):
            return dict(base, reasons=["ARCHITECT_OR_SOURCE_CHANGED"])
        from .policy_gate import evaluate_problem_review_policy, plan_digest
        selected = PlanSpec.validate(fresh["plan_specs"][selected_id])
        decision = evaluate_problem_review_policy(
            problem, selected, architect_truth=fresh["truth_status"],
            evidence_review_required=fresh["evidence_review_required"])
        return dict(base, status=decision.disposition,
                    plan_sha256=plan_digest(selected),
                    plan_id=selected_id, steps=selected.steps,
                    budget=selected.budget, risk=problem.risk,
                    permissions=problem.permissions,
                    reasons=decision.reason_codes,
                    source_sha256=next(s for a, s in zip(
                        fresh["alternatives"], fresh["source_sets"])
                        if a["alternative_id"] == selected_id),
                    preview_only=decision.disposition == "PURE_SYNTHETIC_PREVIEW_ONLY",
                    can_execute_real_actions=False)

    @staticmethod
    def play_reviewed_pure_plan(problem_raw: dict, design: dict, selection: dict,
                                axnode_root: str | Path | None, *,
                                acknowledged_pure_only: bool = False,
                                cancel_before_step: str | None = None) -> dict:
        """Exact revalidation -> policy -> bounded PURE no-op -> replay receipt.

        This is not tool execution: no original writes, arbitrary shell, network,
        memory promotion, new approval or non-pure operator interpretation.
        """
        base = {"kind": "REVIEWED_PURE_PLAYER", "execution": "NOT_EXECUTED",
                "external_actions": 0, "original_writes": 0,
                "verified_real_world": False, "can_promote": False,
                "independent_verification": "NOT_ESTABLISHED"}
        if acknowledged_pure_only is not True:
            return dict(base, status="HOLD_PURE_SIMULATION_CONFIRMATION")
        if type(selection) is not dict or type(selection.get("plan_id")) is not str:
            return dict(base, status="HOLD_PLAN_CHANGED", reasons=["UNREVIEWED_SELECTION"])
        problem = ProblemSpec.validate(problem_raw)
        current = DesktopBridge.inspect_reviewed_selection(
            problem_raw, design, selection["plan_id"], axnode_root)
        if (current.get("status") != "PURE_SYNTHETIC_PREVIEW_ONLY" or
                selection.get("status") != current.get("status") or
                selection.get("problem_sha256") != current.get("problem_sha256") or
                selection.get("plan_sha256") != current.get("plan_sha256") or
                selection.get("source_sha256") != current.get("source_sha256") or
                selection.get("steps") != current.get("steps")):
            return dict(base, status="HOLD_PLAN_CHANGED", reasons=["POLICY_OR_SOURCE_CHANGED"])
        plan = PlanSpec.validate(design["plan_specs"][selection["plan_id"]])
        from .policy_gate import evaluate_problem_review_policy
        from .player_runtime import run_bounded_pure_player, execute_pure_synthetic_preview
        policy = evaluate_problem_review_policy(
            problem, plan, architect_truth="UNVERIFIED", evidence_review_required=False)
        if policy.disposition != "PURE_SYNTHETIC_PREVIEW_ONLY":
            return dict(base, status="HOLD_POLICY_DENIED", reasons=list(policy.reason_codes))
        flow = run_bounded_pure_player(
            problem, plan, interpret_pure_noop=True,
            architect_truth="UNVERIFIED", evidence_review_required=False,
            cancel_before_step=cancel_before_step)
        trace = execute_pure_synthetic_preview(
            problem, plan, policy, cancel_before_step=cancel_before_step)
        if (flow.trace_sha256 != trace.trace_sha256 or
                flow.interpreted_steps != len(trace.step_receipts) or
                flow.replay_status != "PURE_TRACE_REPLAY_MATCH_UNVERIFIED" or
                flow.original_writes or flow.external_actions or trace.promotion_authorized):
            raise ValueError("pure replay/source integrity failed")
        return dict(base, status=flow.status,
                    execution="PURE_SYNTHETIC_NOOP_ONLY", plan_sha256=flow.plan_sha256,
                    problem_sha256=flow.problem_sha256, trace_sha256=flow.trace_sha256,
                    interpreted_steps=flow.interpreted_steps,
                    reasons=list(flow.reason_codes), replay=flow.replay_status,
                    step_observations=[
                        {"id": receipt.step_id, "status": receipt.status,
                         "sha256": receipt.step_sha256}
                        for receipt in trace.step_receipts],
                    cancel_before_step=cancel_before_step,
                    synthetic_only=True)

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
