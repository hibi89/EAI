"""Explicit local untrusted observation intake and Architect replay.

Only a caller-selected existing AXNODE root may receive additive observations.
This path never certifies truth, promotes skills, sends data, or writes legacy DB.
"""
from __future__ import annotations

from pathlib import Path

from .axnode_store import AXNodeStore
from .evidence_ledger import EvidenceLedger
from .architect_runtime import preview_architecture


def ingest_local_claim_and_preview(
    problem_file: str | Path, axnode_root: str | Path, *,
    claim_id: str, source_sha256: str, polarity: str,
    observed_at: int, expires_at: int, now: int | None = None,
) -> dict:
    """Return the updated Architect uncertainty, never a VERIFIED result.

    Fail on unknown or mismatched source before opening a writable sidecar.
    Caller explicitly chooses the node library and time-bounded observation.
    """
    root = Path(axnode_root).expanduser()
    if (root.is_symlink() or not root.is_dir()
            or not (root / "axnodes.sqlite").is_file()
            or (root / "axnodes.sqlite").is_symlink()
            or not (root / "nodes").is_dir()
            or (root / "nodes").is_symlink()):
        raise ValueError("pre-existing explicit AXNODE root required")
    # Reject an invalid ProblemSpec before any evidence append.
    prior = preview_architecture(problem_file, root)
    with AXNodeStore(root) as store:
        pinned = store.get(source_sha256)
        if pinned.as_dict()["id"] != claim_id:
            raise ValueError("claim must match its pinned local AXNODE id")
        path = root / "evidence_ledger.sqlite"
        if path.is_symlink():
            raise ValueError("symlinked evidence ledger forbidden")
        existed = path.exists()
        with EvidenceLedger(
            store, create=not existed, append_existing=existed
        ) as ledger:
            receipt_sha = ledger.append(
                claim_id=claim_id, source_sha256=source_sha256,
                polarity=polarity, observed_at=observed_at,
                expires_at=expires_at, now=now)
            assessment = ledger.assess(claim_id, now=now)
    revised = preview_architecture(problem_file, root)
    if revised["problem_sha256"] != prior["problem_sha256"]:
        raise ValueError("problem changed during local evidence review")
    return {
        "schema": "eai.architect.local_observation.v1",
        "observation_sha256": receipt_sha,
        "claim_id": assessment.claim_id,
        "claim_state": assessment.state,
        "trust": "LOCAL_UNTRUSTED_OBSERVATION_ONLY",
        "architect_preview": revised,
        "verified_real_world": False,
        "permits_execution": False,
        "permits_promotion": False,
    }
