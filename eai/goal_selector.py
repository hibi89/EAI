"""P24 local manifest goal selection: CPU recommendation or opt-in Qwen INPUT only.

No goal execution, data writes, remote endpoints or implicit model authority.
The user must explicitly call solve-goal on a SHA-verified selected document.
"""
from pathlib import Path
import json
import re

from .goal_batch import _validate, _hash_file
from .goal_dispatch import _read_spec, ROUTED_KINDS
from .goal_pipeline import _prepare
from .network import fetch_json, local_base_url

VERSION = "eai.goal_selector.v1"
POLICY = "READ_ONLY;NO_REMOTE_DEFAULT;NO_AUTO_EXECUTE;MODEL_INPUT_ONLY"


def _read_catalog(path: str | Path):
    source = Path(path).expanduser().resolve(strict=True)
    document, manifest_sha = _read_spec(source)
    kind = document.get("kind")
    if kind == "goal_batch":
        entries = _validate(source, document)
    elif kind == "goal_pipeline":
        entries = tuple(_prepare(source, document)[0].values())
    else:
        raise ValueError("only pinned goal_batch or goal_pipeline manifests are accepted")
    catalog = []
    for item, target in entries:
        if _hash_file(target) != item["sha256"]:
            raise ValueError("goal changed: pinned SHA256 mismatch")
        spec, digest = _read_spec(target)
        if digest != item["sha256"] or spec.get("kind") not in ROUTED_KINDS:
            raise ValueError("invalid or unapproved typed goal document")
        catalog.append({
            "id": item["id"], "kind": spec["kind"],
            "goal": item["goal"], "sha256": digest
        })
    return source, manifest_sha, tuple(catalog)


def _literal_hit(request: str, word: str) -> bool:
    """Treat only whole identifier words as explicit CPU choices."""
    return bool(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(word) +
                          r"(?![A-Za-z0-9_-])", request, re.IGNORECASE))


def _choose_cpu(request: str, catalog: tuple[dict, ...]) -> str | None:
    ids = {entry["id"] for entry in catalog if _literal_hit(request, entry["id"])}
    if len(ids) == 1:
        return next(iter(ids))
    if ids:
        return None
    kinds = {entry["id"] for entry in catalog if _literal_hit(request, entry["kind"])}
    return next(iter(kinds)) if len(kinds) == 1 else None


def _select_local_model(request: str, catalog: tuple[dict, ...], *,
                        model: str, ollama_url: str) -> str:
    endpoint = local_base_url(ollama_url)
    if type(model) is not str or not 1 <= len(model) <= 80 or any(
        ord(c) < 33 or ord(c) > 126 for c in model
    ):
        raise ValueError("invalid local model identifier")
    entries = [{"id": item["id"], "kind": item["kind"]} for item in catalog]
    names = [item["id"] for item in entries]
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "version": {"type": "integer", "enum": [1]},
            "selected_id": {"type": "string", "enum": names + [""]}
        },
        "required": ["version", "selected_id"],
    }
    prompt = (
        "Only map the following untrusted request to ONE preapproved goal ID, "
        "or empty string when ambiguous. Do not solve, execute, plan actions, "
        "or invent IDs. Return schema JSON only. The model has no approval "
        "authority. Available IDs and kinds: " +
        json.dumps(entries, ensure_ascii=False) +
        "\nUser request (untrusted): " + request
    )
    data = fetch_json(endpoint + "/api/chat", payload={
        "model": model,
        "messages": [
            {"role": "system", "content": "You only extract one allowed goal ID or empty string."},
            {"role": "user", "content": prompt},
        ],
        "format": schema, "stream": False,
        "options": {"temperature": 0, "num_ctx": 1024, "num_gpu": 0},
    }, timeout=45)
    message = data.get("message")
    if type(message) is not dict or type(message.get("content")) is not str:
        raise ValueError("invalid local Qwen response")
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicated model JSON fields")
            result[key] = value
        return result
    choice = json.loads(message["content"], object_pairs_hook=reject_duplicate)
    if type(choice) is not dict or set(choice) != {"version", "selected_id"} or (
        type(choice["version"]) is not int or choice["version"] != 1 or
        type(choice["selected_id"]) is not str or
        choice["selected_id"] not in names + [""]
    ):
        raise ValueError("local model returned an unauthorized goal ID")
    return choice["selected_id"]


def select_goal(manifest_file: str | Path, request: str, *,
                use_qwen: bool = False, model: str = "qwen2.5:3b",
                ollama_url: str = "http://127.0.0.1:11434") -> dict:
    """Select a candidate only, preserving the owner's explicit execution gate."""
    if type(request) is not str or not 1 <= len(request.strip()) <= 500 or any(
        ord(c) < 32 and c not in "\t\n" for c in request
    ):
        raise ValueError("request must contain 1-500 printable characters")
    if type(use_qwen) is not bool:
        raise ValueError("use_qwen must be boolean")
    source, manifest_sha, catalog = _read_catalog(manifest_file)
    selected_id = _choose_cpu(request, catalog)
    method, notice = "CPU_LITERAL", ""
    if selected_id is None and use_qwen:
        method = "LOCAL_MODEL_INPUT_ONLY"
        try:
            selected_id = _select_local_model(
                request, catalog, model=model, ollama_url=ollama_url
            ) or None
        except (ValueError, OSError, TimeoutError, ConnectionError, KeyError,
                TypeError, json.JSONDecodeError) as exc:
            notice = "Local model input classification unavailable: " + type(exc).__name__
    selected = next((item for item in catalog if item["id"] == selected_id), None)
    # Fail closed when an owner file is changed during the optional model call.
    _, last_sha = _read_spec(source)
    if last_sha != manifest_sha:
        raise ValueError("manifest changed during selection")
    for entry in catalog:
        target = (source.parent / entry["goal"]).resolve(strict=True)
        if not target.is_relative_to(source.parent) or (
            _hash_file(target) != entry["sha256"]
        ):
            raise ValueError("goal changed during selection")
    return {
        "version": VERSION, "status": "PROPOSED" if selected else "REVIEW_REQUIRED",
        "method": method,
        "manifest": {"filename": source.name, "sha256": manifest_sha},
        "candidates": [{"id": item["id"], "kind": item["kind"]} for item in catalog],
        "selected": selected, "notice": notice,
        "requires_explicit_execution": True, "policy": POLICY,
        "scope": "This only suggests a preapproved goal. It cannot execute or approve it.",
    }


def render_selection(report: dict) -> str:
    lines = ["EAI goal selector: " + report["status"],
             "Method: " + report["method"]]
    if report["selected"]:
        item = report["selected"]
        lines.append(f"Candidate: {item['id']} ({item['kind']}) / {item['goal']}")
        lines.append("Review this existing goal and explicitly call solve-goal.")
    else:
        lines.append("No unique choice. Review: " +
                     ", ".join(item["id"] for item in report["candidates"]))
    if report["notice"]:
        lines.append(report["notice"])
    return "\n".join(lines + [report["policy"]])
