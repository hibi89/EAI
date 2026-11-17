"""Read-only local CLI path into C17/C18 synthetic ranking, no real action."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path

from .axnode_store import AXNodeStore
from .b0_cli import _local_json, _SHA
from .contracts import MAX_DOCUMENT_BYTES, ProblemSpec
from .logic_synthesis import LogicSynthesizer
from .strategy_research_ranker import rank_synthetic_strategy_previews
from .synthetic_curriculum import generate_synthetic_curriculum


def preview_strategy(problem_file: str | Path, axnode_root: str | Path,
                     node_hashes: str, *, seed: int = 0) -> dict:
    if type(node_hashes) is not str or len(node_hashes) > 4 * 65:
        raise ValueError("bounded hashes required")
    nodes = tuple(node_hashes.split(","))
    if (not 2 <= len(nodes) <= 4 or len(set(nodes)) != len(nodes)
            or any(not _SHA.fullmatch(x) for x in nodes)):
        raise ValueError("two to four unique hashes required")
    root = Path(axnode_root).expanduser()
    if (root.is_symlink() or not root.is_dir()
            or not (root / "axnodes.sqlite").is_file()
            or (root / "axnodes.sqlite").is_symlink()
            or (root / "nodes").is_symlink()
            or not (root / "nodes").is_dir()):
        raise ValueError("existing explicit local store required")
    problem = ProblemSpec.validate(
        _local_json(problem_file, max_bytes=MAX_DOCUMENT_BYTES))
    curriculum = generate_synthetic_curriculum(seed)
    with AXNodeStore(root) as store:
        candidate = LogicSynthesizer(store).compose(problem, nodes)
        result = rank_synthetic_strategy_previews(
            store, problem, (candidate,), curriculum)
    return {
        "schema": "eai.strategy.preview.v1",
        "status": result.disposition,
        "problem_sha256": result.problem_sha256,
        "curriculum_sha256": result.curriculum_sha256,
        "rank": asdict(result),
        "real_world_verified": False,
        "automatic_learning": False,
        "auto_activation": False,
        "network": "DISABLED_BY_DESIGN",
    }
