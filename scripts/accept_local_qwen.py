"""Offline fixture-only acceptance of genuine LOCAL Ollama/Qwen INPUT classification.

This script never loads customer files, uploads data, runs model-generated
instructions, installs a runtime or modifies the EAI user's originals.
It returns NOT_VERIFIED if real localhost model inference is unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from eai.goal_selector import select_goal
from eai.network import local_base_url
from eai.approved_run import run_approved

ROOT = Path(__file__).resolve().parents[1]
REQUEST = "Please inspect which purchase records point to missing products."
EXPECTED_ID = "references"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8")


def make_synthetic_catalog(directory: Path) -> Path:
    """Use only committed synthetic examples, never a user-supplied path."""
    fixture = ROOT / "examples"
    for name in ("sample_master_keys.csv", "sample_detail_keys.csv"):
        shutil.copyfile(fixture / name, directory / name)
    original = json.loads((fixture / "sample_key_coverage_goal.json").read_text("utf-8"))
    goal = directory / "references.json"
    _write_json(goal, original)
    schedule = directory / "schedule.json"
    _write_json(schedule, {
        "version": 1, "kind": "schedule_tasks",
        "goal": "Synthetic dependency review", "deadline_hours": "3",
        "tasks": [
            {"id": "build", "hours": "1", "requires": []},
            {"id": "qa", "hours": "1", "requires": ["build"]},
        ],
    })
    items = []
    for identifier, filename in ((EXPECTED_ID, "references.json"),
                                 ("scheduler", "schedule.json")):
        raw = (directory / filename).read_bytes()
        items.append({"id": identifier, "goal": filename,
                      "sha256": hashlib.sha256(raw).hexdigest()})
    manifest = directory / "manifest.json"
    _write_json(manifest, {"version": 1, "kind": "goal_batch",
                           "continue_on_error": False, "items": items})
    return manifest


def accept_local_qwen(*, url: str = "http://127.0.0.1:11434",
                      model: str = "qwen2.5:3b",
                      acknowledge: bool = False,
                      approve_synthetic_run: bool = False) -> dict:
    """Never mistake a mock/server failure or CPU fallback for genuine Qwen PASS."""
    if acknowledge is not True:
        return {"status": "BLOCKED", "code": "EXPLICIT_LOCAL_MODEL_ACK_REQUIRED"}
    endpoint = local_base_url(url)
    if type(model) is not str or not 1 <= len(model) <= 80 or any(
        ord(c) < 33 or ord(c) > 126 for c in model
    ):
        raise ValueError("invalid local model identifier")
    with tempfile.TemporaryDirectory(prefix="eai-local-model-synthetic-") as tmp:
        workspace = Path(tmp)
        manifest = make_synthetic_catalog(workspace)
        before = {x.name: hashlib.sha256(x.read_bytes()).hexdigest()
                  for x in workspace.iterdir() if x.is_file()}
        result = select_goal(manifest, REQUEST, use_qwen=True, model=model,
                             ollama_url=endpoint)
        after = {x.name: hashlib.sha256(x.read_bytes()).hexdigest()
                 for x in workspace.iterdir() if x.is_file()}
        if before != after:
            return {"status": "REJECTED", "code": "SOURCE_CHANGED"}
        if result["method"] != "LOCAL_MODEL_INPUT_ONLY":
            return {"status": "REJECTED", "code": "MODEL_NOT_USED"}
        if result["selected"] is None:
            return {"status": "BLOCKED", "code": "LOCAL_MODEL_NOT_VERIFIED"}
        if (result["selected"]["id"] != EXPECTED_ID or
                result["status"] != "PROPOSED" or
                result["requires_explicit_execution"] is not True):
            return {"status": "REJECTED", "code": "MODEL_SELECTION_MISMATCH"}
        report = {"status": "PASS", "scope": "LOCAL_QWEN_INPUT_ONLY",
                  "selected_id": EXPECTED_ID,
                  "approval": "SEPARATE_EXPLICIT_EXECUTION_REQUIRED",
                  "source_modified": False, "customer_data": False}
        if approve_synthetic_run:
            proof = run_approved(
                manifest, EXPECTED_ID, result["manifest"]["sha256"],
                result["selected"]["sha256"])
            if (proof["status"] != "AGREE" or not proof["verified"] or
                    proof["authorization"]["mode"] != "SEPARATE_EXPLICIT_CALL" or
                    proof["receipt"]["verification"]["status"] != "PASS"):
                return {"status": "REJECTED", "code": "CPU_RECEIPT_FAILED"}
            final = {x.name: hashlib.sha256(x.read_bytes()).hexdigest()
                     for x in workspace.iterdir() if x.is_file()}
            if final != before:
                return {"status": "REJECTED", "code": "SOURCE_CHANGED_AFTER_CPU"}
            report["synthetic_cpu_receipt"] = "PASS"
        return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Real localhost Qwen synthetic gate")
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--ack-local-model", action="store_true",
                        help="explicitly consent to SYNTHETIC-only localhost model request")
    parser.add_argument("--approve-synthetic-run", action="store_true",
                        help="separate explicit execution of synthetic CPU goal only")
    args = parser.parse_args(argv)
    try:
        result = accept_local_qwen(url=args.url, model=args.model,
                                   acknowledge=args.ack_local_model,
                                   approve_synthetic_run=args.approve_synthetic_run)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        result = {"status": "BLOCKED", "code": "LOCAL_MODEL_GATE_ERROR",
                  "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return {"PASS": 0, "REJECTED": 2, "BLOCKED": 3}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
