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
        if problem.risk == "HIGH":
            raise ValueError("high risk composition requires independent owner review")
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
        nodes: list[dict] = []
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


# EAI P1 SWU 018: bounded declarative DSL, no evaluation or generated code.
@dataclass(frozen=True)
class TypedCompositionStep:
    node_sha256: str
    operator: str
    required_inputs: tuple[str, ...]
    output_type: str
    effect: str


@dataclass(frozen=True)
class BoundedCompositionProgram:
    grammar: str
    problem_sha256: str
    statements: tuple[TypedCompositionStep, ...]
    candidate_sha256: str
    program_sha256: str
    status: str = "STRUCTURE_ONLY_UNVERIFIED"


def compile_bounded_composition(synth: LogicSynthesizer,
                                problem: ProblemSpec,
                                node_hashes: tuple[str, ...]
                                ) -> BoundedCompositionProgram:
    """Check real pinned types/effects before emitting only data-shaped DSL."""
    if type(synth) is not LogicSynthesizer:
        raise ValueError("explicit local synthesizer required")
    candidate = synth.compose(problem, node_hashes)
    statements: list[TypedCompositionStep] = []
    previous_output = None
    for digest in candidate.node_hashes:
        node = synth.store.get(digest)
        if node.sha256 != digest:
            raise ValueError("stale DSL input")
        raw = node.as_dict()
        inputs = tuple(sorted(raw["signature"]["inputs"].values()))
        output = raw["signature"]["output"]
        if previous_output is not None and previous_output not in inputs:
            raise ValueError("DSL chain has incompatible typed effect")
        ops = tuple(step["skill"] for step in raw["steps"])
        if not ops or any(op not in _ALLOWED for op in ops):
            raise ValueError("unsafe DSL operator")
        if len(statements) + len(ops) > problem.budget[0]:
            raise ValueError("DSL step budget exceeded")
        for op in ops:
            effect = "local.read" if op == "csv.reconcile.v1" else "pure"
            if effect not in problem.permissions or (
                    effect == "local.read" and effect not in raw["capabilities"]):
                raise ValueError("DSL effect capability denied")
            statements.append(TypedCompositionStep(
                digest, op, inputs, output, effect))
        previous_output = output
    grammar = "sequence.pinned.typed.v1"
    serial = {
        "grammar": grammar,
        "problem_sha256": problem.digest(),
        "statements": [
            {"source": s.node_sha256, "operator": s.operator,
             "inputs": list(s.required_inputs), "output": s.output_type,
             "effect": s.effect} for s in statements],
        "candidate_sha256": candidate.candidate_sha256,
        "status": "STRUCTURE_ONLY_UNVERIFIED",
    }
    return BoundedCompositionProgram(
        grammar, problem.digest(), tuple(statements),
        candidate.candidate_sha256,
        hashlib.sha256(canonical_bytes(serial)).hexdigest())
