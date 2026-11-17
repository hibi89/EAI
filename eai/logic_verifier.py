"""Independent *structural only* recomputation of EAI synthesis proposals.

No executable plan, oracle correctness, independent evidence or activation
is ever certified by this verifier. Structurally valid != safe to execute.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .contracts import ProblemSpec
from .axnode_store import AXNodeStore
from .logic_synthesis import SynthesisCandidate, _composition_bytes

_ALLOWED = frozenset({"csv.reconcile.v1", "evidence.verify_receipt.v1"})


@dataclass(frozen=True)
class StructuralReceipt:
    candidate_sha256: str
    status: str
    reason: str
    semantic_verified: bool = False
    permits_execution: bool = False


class StructuralVerifier:
    def __init__(self, store: AXNodeStore):
        if type(store) is not AXNodeStore:
            raise ValueError("explicit AXNODE store required")
        self.store = store

    def check(self, problem: ProblemSpec,
              candidate: SynthesisCandidate) -> StructuralReceipt:
        if type(problem) is not ProblemSpec or type(candidate) is not SynthesisCandidate:
            raise ValueError("typed candidate and problem required")
        failed = StructuralReceipt(candidate.candidate_sha256, "REJECTED_UNVERIFIED",
                                   "UNTRUSTED_COMPOSITION_OR_PROVENANCE")
        hashes = candidate.node_hashes
        if (candidate.trust != "LOCAL_SYNTHESIS_UNVERIFIED" or
                candidate.problem_sha256 != problem.digest() or
                type(hashes) is not tuple or not 2 <= len(hashes) <= 4 or
                len(set(hashes)) != len(hashes) or
                any(type(h) is not str or len(h) != 64 for h in hashes) or
                type(candidate.step_count) is not int or
                type(candidate.predicted_seconds) is not int):
            return failed
        try:
            total_steps, total_seconds = 0, 0
            previous = None
            ids = set()
            for index, digest in enumerate(hashes):
                node = self.store.get(digest)
                if node.sha256 != digest:
                    return failed
                raw = node.as_dict()
                if raw["id"] in ids or raw["status"] not in ("DRAFT", "CANDIDATE"):
                    return failed
                ids.add(raw["id"])
                if raw["parent_hashes"] != ([] if index == 0 else [hashes[index - 1]]):
                    return failed
                if previous is not None and previous not in raw["signature"]["inputs"].values():
                    return failed
                for step in raw["steps"]:
                    operator = step["skill"]
                    if operator not in _ALLOWED:
                        return failed
                    if operator == "csv.reconcile.v1" and (
                            "local.read" not in problem.permissions or
                            "local.read" not in raw["capabilities"]):
                        return failed
                previous = raw["signature"]["output"]
                total_steps += len(raw["steps"])
                total_seconds += raw["budget"]["max_seconds"]
            required, forbidden = set(), set()
            for clause in problem.hard_constraints:
                if clause.startswith("must:"):
                    required.add(clause[5:])
                elif clause.startswith("forbid:"):
                    forbidden.add(clause[7:])
                else:
                    return failed
            if (required & forbidden or not required.issubset(ids) or ids & forbidden or
                    total_steps > problem.budget[0] or
                    total_seconds > problem.budget[1] or
                    candidate.step_count != total_steps or
                    candidate.predicted_seconds != total_seconds):
                return failed
            actual_digest = hashlib.sha256(_composition_bytes(
                problem.digest(), hashes, total_steps, total_seconds)).hexdigest()
            if actual_digest != candidate.candidate_sha256:
                return failed
        except (KeyError, ValueError, OSError, TypeError):
            return failed
        return StructuralReceipt(candidate.candidate_sha256,
                                 "STRUCTURE_ONLY_UNVERIFIED",
                                 "INDEPENDENT_SEMANTIC_ORACLE_NOT_RUN")
