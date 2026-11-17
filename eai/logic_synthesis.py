"""Restricted AXNODE composition proposals; pure structure, never code execution.

These candidates cannot become VERIFIED/ACTIVE without independent semantic
oracle, separate promotion policy, heldout tests and explicit user authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .contracts import ProblemSpec, canonical_bytes
from .axnode_store import AXNodeStore

_ALLOWED = frozenset({"csv.reconcile.v1", "evidence.verify_receipt.v1"})
_MAX_NODES = 4


def _composition_bytes(problem_digest: str, node_hashes: tuple[str, ...],
                       step_count: int, seconds: int) -> bytes:
    return canonical_bytes({
        "schema": "eai.synthesis.v1", "problem_sha256": problem_digest,
        "node_hashes": list(node_hashes), "step_count": step_count,
        "predicted_seconds": seconds, "trust": "LOCAL_SYNTHESIS_UNVERIFIED",
    })


@dataclass(frozen=True)
class SynthesisCandidate:
    problem_sha256: str
    node_hashes: tuple[str, ...]
    step_count: int
    predicted_seconds: int
    candidate_sha256: str
    trust: str = "LOCAL_SYNTHESIS_UNVERIFIED"


class LogicSynthesizer:
    """Only a 2–4-node linear typed composition; no arbitrary expression DSL."""

    def __init__(self, store: AXNodeStore):
        if type(store) is not AXNodeStore:
            raise ValueError("explicit local AXNODE store required")
        self.store = store

    def compose(self, problem: ProblemSpec,
                node_hashes: tuple[str, ...]) -> SynthesisCandidate:
        if type(problem) is not ProblemSpec:
            raise ValueError("typed problem required")
        if (type(node_hashes) is not tuple or not 2 <= len(node_hashes) <= _MAX_NODES or
                any(type(h) is not str for h in node_hashes) or
                len(set(node_hashes)) != len(node_hashes)):
            raise ValueError("bounded distinct AXNODE chain required")
        required = set()
        forbidden = set()
        for condition in problem.hard_constraints:
            if condition.startswith("must:"):
                required.add(condition[5:])
            elif condition.startswith("forbid:"):
                forbidden.add(condition[7:])
            else:
                raise ValueError("unknown hard constraint requires separate modeling")
        nodes = []
        step_count, seconds = 0, 0
        for index, h in enumerate(node_hashes):
            node = self.store.get(h)
            if node.sha256 != h:
                raise ValueError("stale AXNODE content address")
            raw = node.as_dict()
            if raw["status"] not in ("DRAFT", "CANDIDATE"):
                raise ValueError("untrusted AXNODE lifecycle status")
            parents = raw["parent_hashes"]
            if parents != ([] if index == 0 else [node_hashes[index - 1]]):
                raise ValueError("unbounded or disconnected dependency graph")
            if index > 0 and nodes[-1]["signature"]["output"] not in raw["signature"]["inputs"].values():
                raise ValueError("parent output type cannot satisfy child input")
            if any(step["skill"] not in _ALLOWED for step in raw["steps"]):
                raise ValueError("unapproved composition operator")
            for step in raw["steps"]:
                permission = "local.read" if step["skill"] == "csv.reconcile.v1" else "pure"
                if permission == "local.read" and (
                        permission not in problem.permissions or permission not in raw["capabilities"]):
                    raise ValueError("composition capability exceeds permission")
            nodes.append(raw)
            step_count += len(raw["steps"])
            seconds += raw["budget"]["max_seconds"]
        ids = {raw["id"] for raw in nodes}
        if (required & forbidden or not required.issubset(ids) or ids & forbidden):
            raise ValueError("composition violates hard requirements")
        if step_count > problem.budget[0] or seconds > problem.budget[1]:
            raise ValueError("composition resource budget exceeded")
        digest = hashlib.sha256(_composition_bytes(
            problem.digest(), node_hashes, step_count, seconds)).hexdigest()
        return SynthesisCandidate(problem.digest(), node_hashes,
                                  step_count, seconds, digest)
