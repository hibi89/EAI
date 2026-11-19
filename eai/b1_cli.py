"""Explicit local synthetic-only B1 candidate-vs-B0 preview.

The candidate interpreter is limited to csv.reconcile.v1 in-memory steps.
Never interprets arbitrary Python, imports plugins, promotes AXNODEs, trains
a model, or opens original customer CSV files. Output is aggregate only.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .axnode_store import AXNodeStore
from .b0_cli import _local_json, _fixture, _SHA, _MAX_FIXTURE_FILE
from .contracts import MAX_DOCUMENT_BYTES, ProblemSpec
from .logic_synthesis import LogicSynthesizer
from .synthetic_candidate_benchmark import benchmark_synthetic_candidate


def b1_preview(problem_file: str | Path, axnode_root: str | Path,
               fixture_file: str | Path, node_hashes: str) -> dict:
    if type(node_hashes) is not str or len(node_hashes) > 4 * 65:
        raise ValueError("bounded explicit AXNODE hashes required")
    refs = tuple(node_hashes.split(","))
    if (not 2 <= len(refs) <= 4 or len(set(refs)) != len(refs) or
            any(not _SHA.fullmatch(ref) for ref in refs)):
        raise ValueError("two to four distinct AXNODE hashes required")
    root = Path(axnode_root).expanduser()
    if (root.is_symlink() or not root.is_dir() or
            not (root / "axnodes.sqlite").is_file() or
            (root / "axnodes.sqlite").is_symlink() or
            not (root / "nodes").is_dir() or
            (root / "nodes").is_symlink()):
        raise ValueError("existing explicit local AXNODE store required")
    problem = ProblemSpec.validate(_local_json(
        problem_file, max_bytes=MAX_DOCUMENT_BYTES))
    payload = _local_json(fixture_file, max_bytes=_MAX_FIXTURE_FILE)
    if (type(payload) is not dict or
            set(payload) != {"version","train","heldout"} or
            type(payload["version"]) is not int or payload["version"] != 1):
        raise ValueError("strict synthetic fixture manifest required")
    from .logic_oracle import SyntheticComparison
    train: list[SyntheticComparison] = []
    heldout: list[SyntheticComparison] = []
    for key, group in (("train",train),("heldout",heldout)):
        items=payload[key]
        if type(items) is not list or not 2 <= len(items) <= 12:
            raise ValueError("bounded synthetic fixture split required")
        group.extend(_fixture(item) for item in items)
    with AXNodeStore(root) as store:
        candidate = LogicSynthesizer(store).compose(problem, refs)
        report = benchmark_synthetic_candidate(
            store, problem, candidate, tuple(train), tuple(heldout))
    return {
        "schema": "eai.synthetic.b1.preview.v1",
        "problem_sha256": problem.digest(),
        "candidate_sha256": candidate.candidate_sha256,
        "comparison": asdict(report),
        "candidate_synthetic_only": True,
        "real_world_verified": False,
        "automatic_learning": False,
        "node_activation": False,
        "network": "DISABLED_BY_DESIGN",
    }
