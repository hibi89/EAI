"""P38: offline-only comparison of owner-pinned input-classifier proposals.

This script NEVER calls a model, GitHub, sockets or a paid API. It parses only
synthetic, owner-prepared predictions and produces aggregate metrics to stdout.
It is deliberately outside the packaged EAI runtime; it has no action authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from eai.goal_selector import _read_catalog, _choose_cpu

VERSION = "eai.model_candidate_benchmark.v1"
MAX_BYTES = 131072
MAX_CASES = 100
MAX_PREDICTIONS = 400
ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
MODEL = re.compile(r"^[a-z0-9_-]{1,40}$")


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _load(path):
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError("fixture must be an existing regular file, not a symlink")
    if source.stat().st_size > MAX_BYTES:
        raise ValueError("fixture exceeds byte limit")
    return json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=_unique)


def _choice(raw, allowed):
    if type(raw) is not str or len(raw) > 4096:
        return None
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, TypeError):
        return None
    if (type(value) is not dict or set(value) != {"version", "selected_id"}
            or type(value["version"]) is not int or value["version"] != 1
            or type(value["selected_id"]) is not str
            or value["selected_id"] not in allowed):
        return None
    return value["selected_id"]


def _scores(values, expected):
    score = {"correct": 0, "wrong": 0, "invalid": 0,
             "missing": 0, "abstain": 0, "total": len(expected)}
    for case_id, truth in expected.items():
        if case_id not in values:
            score["missing"] += 1
        elif values[case_id] is None:
            score["invalid"] += 1
        else:
            choice = values[case_id]
            if choice == "":
                score["abstain"] += 1
            score["correct" if choice == truth else "wrong"] += 1
    return score


def compare(manifest_file, cases_file, predictions_file):
    """Compare precomputed labels only. No network, execution or file changes."""
    _, manifest_sha, catalog = _read_catalog(manifest_file)
    allowed = {item["id"] for item in catalog} | {""}
    cases_doc = _load(cases_file)
    preds_doc = _load(predictions_file)
    if (type(cases_doc) is not dict or set(cases_doc) != {"version", "cases"}
            or type(cases_doc["version"]) is not int or cases_doc["version"] != 1
            or type(cases_doc["cases"]) is not list
            or not 1 <= len(cases_doc["cases"]) <= MAX_CASES):
        raise ValueError("invalid cases fixture contract")
    if (type(preds_doc) is not dict or set(preds_doc) != {"version", "predictions"}
            or type(preds_doc["version"]) is not int or preds_doc["version"] != 1
            or type(preds_doc["predictions"]) is not list
            or len(preds_doc["predictions"]) > MAX_PREDICTIONS):
        raise ValueError("invalid prediction fixture contract")
    expected, cpu = {}, {}
    for case in cases_doc["cases"]:
        if (type(case) is not dict or set(case) != {"id", "request", "expected_id"}
                or type(case["id"]) is not str or not ID.fullmatch(case["id"])
                or case["id"] in expected or type(case["request"]) is not str
                or not 1 <= len(case["request"].strip()) <= 500
                or any(ord(ch) < 32 and ch not in "\t\n" for ch in case["request"])
                or type(case["expected_id"]) is not str
                or case["expected_id"] not in allowed):
            raise ValueError("invalid case or unapproved expected ID")
        expected[case["id"]] = case["expected_id"]
        cpu_id, ambiguous = _choose_cpu(case["request"], catalog)
        cpu[case["id"]] = "" if ambiguous or cpu_id is None else cpu_id
    models = {}
    for pred in preds_doc["predictions"]:
        if (type(pred) is not dict or set(pred) != {"model", "case_id", "raw_output"}
                or type(pred["model"]) is not str or not MODEL.fullmatch(pred["model"])
                or type(pred["case_id"]) is not str
                or pred["case_id"] not in expected):
            raise ValueError("invalid model prediction or unknown case ID")
        model = pred["model"]
        if model not in models and len(models) >= 4:
            raise ValueError("at most four model labels")
        group = models.setdefault(model, {})
        if pred["case_id"] in group:
            raise ValueError("duplicate model/case prediction")
        group[pred["case_id"]] = _choice(pred["raw_output"], allowed)
    # Catalog may not change while the offline comparison is in progress.
    _, final_sha, final_catalog = _read_catalog(manifest_file)
    if final_sha != manifest_sha or final_catalog != catalog:
        raise ValueError("owner-pinned catalog changed during comparison")
    return {
        "version": VERSION,
        "status": "SYNTHETIC_OFFLINE_EVALUATION_ONLY",
        "manifest_sha256": manifest_sha,
        "cases": len(expected),
        "cpu_literal": _scores(cpu, expected),
        "models": {name: _scores(data, expected)
                   for name, data in sorted(models.items())},
        "privacy": "COUNTS_ONLY;NO_PROMPTS_IN_REPORT;NO_NETWORK;NO_EXECUTION",
        "authority": "NO_MODEL_APPROVAL;CPU_OWNED_DECISIONS_UNCHANGED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline EAI input-only model comparator")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--predictions", required=True)
    args = parser.parse_args(argv)
    try:
        result = compare(args.manifest, args.cases, args.predictions)
    except (ValueError, OSError, UnicodeError) as exc:
        # Neither user requests nor raw model outputs are included in errors.
        print("BLOCKED: invalid local benchmark input (" + type(exc).__name__ + ")", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
