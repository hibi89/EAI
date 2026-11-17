"""Explicit local-only EAI B0 baseline preview; no model, candidate execution or writes.

Fixtures and ProblemSpec are locally supplied strict JSON; output reports
only aggregate synthetic baseline counts and opaque family identifiers.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import re

from .axnode_store import AXNodeStore
from .contracts import MAX_DOCUMENT_BYTES, ProblemSpec, strict_json
from .logic_oracle import SyntheticComparison, _ID, _records
from .logic_synthesis import LogicSynthesizer
from .synthetic_holdout import compare_b0_train_and_heldout

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_FIXTURE_FILE = 64 * 1024


def _local_json(path: str | Path, *, max_bytes: int):
    selected = Path(path).expanduser()
    if (selected.is_symlink() or not selected.is_file() or
            selected.stat().st_size > max_bytes):
        raise ValueError("explicit local regular bounded JSON required")
    return strict_json(selected.read_bytes(), max_bytes=max_bytes)


def _fixture(raw: dict) -> SyntheticComparison:
    if type(raw) is not dict or set(raw) != {
            "family", "left", "right", "claimed_different"}:
        raise ValueError("exact synthetic fixture schema required")
    if type(raw["family"]) is not str or not _ID.fullmatch(raw["family"]):
        raise ValueError("opaque fixture family identifier required")
    datasets = []
    for field in ("left", "right"):
        rows = raw[field]
        if type(rows) is not list:
            raise ValueError("typed synthetic CSV rows required")
        tuples = []
        for pair in rows:
            if type(pair) is not list or len(pair) != 2 or any(
                    type(cell) is not str for cell in pair):
                raise ValueError("synthetic row must contain two bounded strings")
            tuples.append((pair[0], pair[1]))
        values = tuple(tuples)
        _records(values)  # exact finite Decimal, unique key, row and name caps
        datasets.append(values)
    differences = raw["claimed_different"]
    if (type(differences) is not list or len(differences) > 48 or
            any(type(v) is not str or not _ID.fullmatch(v) for v in differences) or
            differences != sorted(set(differences))):
        raise ValueError("sorted bounded difference keys required")
    return SyntheticComparison(raw["family"], datasets[0],
                               datasets[1], tuple(differences))


def b0_preview(problem_file: str | Path, axnode_root: str | Path,
               fixture_file: str | Path, node_hashes: str) -> dict:
    if type(node_hashes) is not str or len(node_hashes) > 4 * 65:
        raise ValueError("bounded comma-separated node hashes required")
    refs = tuple(node_hashes.split(","))
    if (not 2 <= len(refs) <= 4 or len(set(refs)) != len(refs) or
            any(not _SHA.fullmatch(ref) for ref in refs)):
        raise ValueError("two to four distinct exact node hashes required")
    root = Path(axnode_root).expanduser()
    if (root.is_symlink() or not root.is_dir() or
            not (root / "axnodes.sqlite").is_file() or
            (root / "axnodes.sqlite").is_symlink() or
            not (root / "nodes").is_dir() or (root / "nodes").is_symlink()):
        raise ValueError("existing explicit AXNODE root is required")
    problem = ProblemSpec.validate(_local_json(
        problem_file, max_bytes=MAX_DOCUMENT_BYTES))
    raw = _local_json(fixture_file, max_bytes=_MAX_FIXTURE_FILE)
    if (type(raw) is not dict or set(raw) != {"version", "train", "heldout"} or
            type(raw["version"]) is not int or raw["version"] != 1):
        raise ValueError("strict synthetic B0 fixture manifest required")
    splits = []
    for key in ("train", "heldout"):
        group = raw[key]
        if type(group) is not list or not 2 <= len(group) <= 12:
            raise ValueError("two to twelve synthetic fixture families per split")
        splits.append(tuple(_fixture(item) for item in group))
    with AXNodeStore(root) as store:
        candidate = LogicSynthesizer(store).compose(problem, refs)
        report = compare_b0_train_and_heldout(
            store, problem, candidate, splits[0], splits[1])
    return {
        "schema": "eai.synthetic.b0.preview.v1",
        "problem_sha256": problem.digest(),
        "candidate_sha256": candidate.candidate_sha256,
        "baseline": asdict(report),
        "candidate_executed": False,
        "new_strategy_verified": False,
        "automatic_learning": False,
        "node_activation": False,
        "synthetic_only": True,
        "network": "DISABLED_BY_DESIGN",
    }
