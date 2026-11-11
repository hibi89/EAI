"""P28 single-command explicit read-only CPU goal execution, no JSON authoring.

Existing typed P19/P20/P22 solvers and independent receipt guards are reused;
no dynamic code, shell, remote model, original file write or auto-discovery.
"""
from pathlib import Path

from .csv_relationships import (
    validate_relationship_goal, execute_relationship_goal, render_relationships
)
from .csv_robust_outliers import (
    validate_outlier_goal, execute_outlier_goal, render_outliers
)
from .local_evidence_search import (
    validate_search_goal, execute_search_goal, render_search
)
from .receipt_guard import verify_goal_receipt

VERSION = "eai.quick.v1"
POLICY = "EXPLICIT_FILES_ONLY;READ_ONLY;NO_REMOTE;NO_AUTOMATIC_REPAIR"

KINDS = ("csv_relationships", "csv_robust_outliers", "local_evidence_search")


def quick_goal(kind: str, root: str | Path, *, source: str | None = None,
               sources: list[str] | None = None, columns: list[str] | None = None,
               terms: list[str] | None = None, encoding: str = "utf-8-sig",
               min_rows: int = 5, threshold: str = "3", max_results: int = 10,
               include_snippets: bool = False) -> dict:
    if type(kind) is not str or kind not in KINDS:
        raise ValueError("quick mode supports only three existing typed CPU goals")
    folder = Path(root).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("explicit root must be a directory")
    if kind == "csv_relationships":
        if source is None or type(columns) is not list or sources or terms or include_snippets:
            raise ValueError("relationship quick mode requires --source and --columns only")
        raw = {
            "version":1, "kind":kind, "goal":"Explicit numeric relationships",
            "source":source, "encoding":encoding,
            "columns":columns, "min_rows":min_rows,
        }
        goal = validate_relationship_goal(raw, folder / "_unwritten_quick.json")
        result = execute_relationship_goal(goal)
        render = render_relationships
    elif kind == "csv_robust_outliers":
        if source is None or type(columns) is not list or sources or terms or include_snippets:
            raise ValueError("outlier quick mode requires --source and --columns only")
        raw = {
            "version":1, "kind":kind, "goal":"Explicit numeric outlier candidates",
            "source":source, "encoding":encoding,
            "columns":columns, "min_rows":min_rows, "threshold":threshold,
        }
        goal = validate_outlier_goal(raw, folder / "_unwritten_quick.json")
        result = execute_outlier_goal(goal)
        render = render_outliers
    else:
        if source is not None or columns or type(sources) is not list or (
            type(terms) is not list
        ):
            raise ValueError("evidence quick mode requires --sources and --terms")
        if encoding != "utf-8-sig" or min_rows != 5 or threshold != "3":
            raise ValueError("CSV-only options not permitted in evidence quick mode")
        raw = {
            "version":1, "kind":kind, "goal":"Explicit local evidence lookup",
            "sources":sources, "terms":terms,
            "max_results":max_results, "include_snippets":include_snippets,
        }
        goal = validate_search_goal(raw, folder / "_unwritten_quick.json")
        result = execute_search_goal(goal)
        render = render_search
    verified = verify_goal_receipt(kind, goal, result)
    if verified["status"] != "PASS":
        raise ValueError("independent CPU proof failed")
    return {
        "version":VERSION,"kind":kind,"status":result["status"],
        "verification":verified,"result":result,"policy":POLICY,
        "human_report":render(result),
        "scope":"Only explicitly selected existing files were analyzed; no goal JSON written."
    }


def render_quick(report: dict) -> str:
    if report.get("verification",{}).get("status") != "PASS":
        raise ValueError("cannot render an unverified quick receipt")
    return report["human_report"] + "\n" + report["policy"]
