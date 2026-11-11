"""P25 verified read-only execution summary export (stdout-only HTML or JSON).

The report deliberately omits underlying row values, source snippets and private
goal descriptions. The caller explicitly supplies one approved local document.
"""
from html import escape
from pathlib import Path

from .goal_dispatch import _read_spec, execute_goal_document, ROUTED_KINDS
from .goal_batch import execute_batch_document
from .goal_pipeline import execute_pipeline_document

VERSION = "eai.safe_export.v1"
POLICY = "NO_OUTPUT_FILE;NO_NETWORK;NO_RAW_SOURCE_VALUES;NO_AUTO_REPAIR"
DISCLAIMER = (
    "Verified checks describe the selected input and bounded CPU rules only. "
    "They do not establish factual truth, statistical significance, or approval to act."
)


def build_report(source: str | Path) -> dict:
    """Execute an explicitly supplied read-only goal and minimize the receipt."""
    path = Path(source).expanduser().resolve(strict=True)
    parsed, original_sha = _read_spec(path)
    kind = parsed.get("kind")
    if kind in ROUTED_KINDS:
        receipt = execute_goal_document(path)
        if receipt.get("verification", {}).get("status") != "PASS":
            raise ValueError("goal independent verification did not pass")
        if receipt.get("input", {}).get("sha256") != original_sha:
            raise ValueError("goal SHA256 changed")
        rows = [{
            "id": "goal", "kind": receipt["kind"],
            "status": receipt["status"], "verification": "PASS",
            "sha256": receipt["input"]["sha256"],
        }]
        state = receipt["status"]
    elif kind in ("goal_batch", "goal_pipeline"):
        receipt = (execute_batch_document(path) if kind == "goal_batch"
                   else execute_pipeline_document(path))
        if receipt.get("verification", {}).get("status") != "PASS":
            raise ValueError("manifest receipt independent verification did not pass")
        if receipt.get("manifest", {}).get("sha256") != original_sha:
            raise ValueError("manifest SHA256 changed")
        rows = [{
            "id": record["id"], "kind": record["kind"] or "NOT_RUN",
            "status": record["status"], "verification": record["verification"],
            "sha256": record["sha256"],
        } for record in receipt["items"]]
        state = receipt["status"]
    else:
        raise ValueError("unsupported export document kind")
    _, final_sha = _read_spec(path)
    if final_sha != original_sha:
        raise ValueError("document changed during report")
    # The complete nested receipt is intentionally not returned. Raw snippets,
    # customer values and user-defined goal text stay in the existing local CLI.
    return {
        "version": VERSION, "status": state, "kind": kind,
        "document": {"filename": path.name, "sha256": original_sha},
        "verification": "PASS", "items": rows,
        "disclaimer": DISCLAIMER, "policy": POLICY,
    }


def render_report_html(summary: dict) -> str:
    """Static offline HTML. Every input-derived string is escaped."""
    if summary.get("version") != VERSION or summary.get("verification") != "PASS":
        raise ValueError("cannot render an unverified summary")
    e = lambda x: escape(str(x), quote=True)
    items = "".join(
        "<tr>" +
        "".join("<td>" + e(row[col]) + "</td>" for col in
                ("id", "kind", "status", "verification", "sha256")) +
        "</tr>"
        for row in summary["items"]
    )
    css = (
        "body{font:16px/1.55 system-ui,Arial,sans-serif;max-width:920px;"
        "margin:48px auto;padding:0 22px;color:#182333;background:#fff}"
        "h1{font-size:28px}table{border-collapse:collapse;width:100%;"
        "font-size:14px;overflow-wrap:anywhere}th,td{border-bottom:1px solid #ccd4dc;"
        "padding:12px 8px;text-align:left}thead{background:#f2f5f8}"
        "p{overflow-wrap:anywhere}.note{font-size:14px;color:#4b596a}"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; '
        "style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; "
        'form-action &#39;none&#39;">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>EAI verified offline summary</title><style>' + css + '</style>'
        '</head><body><main><h1>EAI verified offline summary</h1>'
        '<p>Status: <strong>' + e(summary["status"]) + '</strong></p>'
        '<p>Document: ' + e(summary["document"]["filename"]) + '</p>'
        '<p class="note">SHA256: ' + e(summary["document"]["sha256"]) + '</p>'
        '<table><thead><tr><th>ID</th><th>Kind</th><th>Status</th>'
        '<th>Check</th><th>Goal SHA256</th></tr></thead><tbody>' + items +
        '</tbody></table><p class="note">' + e(summary["disclaimer"]) + '</p>'
        '<p class="note">' + e(summary["policy"]) +
        '</p></main></body></html>'
    )
