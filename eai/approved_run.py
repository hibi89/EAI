"""P26 explicit local-only goal execution, never authorized by a model guess.

Requires BOTH the selected manifest digest and exact selected goal digest, plus
the owner-entered ID. P14 pipelines must use their dependency-gated runner.
"""
import hashlib
from pathlib import Path

from .goal_batch import _hash_file
from .goal_dispatch import execute_goal_document, _read_spec
from .goal_selector import _read_catalog

VERSION = "eai.approved_run.v1"
POLICY = "EXPLICIT_ID_AND_TWO_SHAS;READ_ONLY;NO_QWEN_AUTHORITY;NO_REMOTE"


def run_approved(manifest_file: str | Path, goal_id: str,
                 manifest_sha256: str, goal_sha256: str) -> dict:
    """Execute a SHA-bound goal only upon the owner's separate explicit call."""
    if any(type(value) is not str or len(value) != 64 or any(
        ch not in "0123456789abcdef" for ch in value
    ) for value in (manifest_sha256, goal_sha256)):
        raise ValueError("both exact lowercase SHA256 digests are required")
    if type(goal_id) is not str or not 1 <= len(goal_id) <= 80:
        raise ValueError("explicit bounded goal ID required")
    source, observed_manifest, catalog = _read_catalog(manifest_file)
    raw, _ = _read_spec(source)
    # P14 dependency checks must not be skipped by a selected child shortcut.
    if raw.get("kind") != "goal_batch":
        raise ValueError("approved single run accepts batch entries only; use pipeline-goals")
    if observed_manifest != manifest_sha256:
        raise ValueError("manifest approval SHA256 does not match")
    selected = next((item for item in catalog if item["id"] == goal_id), None)
    if selected is None:
        raise ValueError("goal ID not in owner-pinned manifest")
    if selected["sha256"] != goal_sha256:
        raise ValueError("selected goal approval SHA256 does not match")
    path = (source.parent / selected["goal"]).resolve(strict=True)
    if not path.is_relative_to(source.parent):
        raise ValueError("selected goal escaped manifest root")
    if _hash_file(path) != goal_sha256:
        raise ValueError("selected goal source changed before execution")
    decision = execute_goal_document(path)
    if decision.get("verification", {}).get("status") != "PASS" or (
        decision.get("input", {}).get("sha256") != goal_sha256
    ):
        raise ValueError("approved goal receipt verification failed")
    # All pinned entries and source manifest must remain immutable, not just
    # the executed one. No unauthorized retry or fallback to another goal.
    _, final_manifest, final_catalog = _read_catalog(source)
    if final_manifest != manifest_sha256 or final_catalog != catalog:
        raise ValueError("pinned goal manifest changed during execution")
    if _hash_file(path) != goal_sha256:
        raise ValueError("selected goal source changed after execution")
    return {
        "version": VERSION, "status": decision["status"], "goal_id": goal_id,
        "authorization": {
            "manifest_sha256": manifest_sha256, "goal_sha256": goal_sha256,
            "mode": "SEPARATE_EXPLICIT_CALL",
        },
        "verified": True, "receipt": decision, "policy": POLICY,
    }
