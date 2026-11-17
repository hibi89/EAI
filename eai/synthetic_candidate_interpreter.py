"""Bounded EAI AXNODE *synthetic-only* candidate interpreter.

Executes an explicit chain of typed csv.reconcile.v1 AXNODE steps on in-memory
synthetic comparisons. This is actual interpretation of the candidate DSL,
NOT access to original CSV files, Qwen, the network, or runtime privileges.
It neither promotes nodes nor produces a real-world verification receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec, canonical_bytes
from .logic_oracle import SyntheticComparison, _ID, _records
from .logic_synthesis import SynthesisCandidate
from .logic_verifier import StructuralVerifier


@dataclass(frozen=True)
class SyntheticStepWitness:
    node_sha256: str
    output_type: str
    step_index: int


@dataclass(frozen=True)
class SyntheticFamilyWitness:
    family: str
    difference_sha256: str
    difference_count: int
    executed_steps: int


@dataclass(frozen=True)
class SyntheticCandidateExecution:
    problem_sha256: str
    candidate_sha256: str
    disposition: str
    steps: tuple[SyntheticStepWitness, ...]
    families: tuple[SyntheticFamilyWitness, ...]
    witness_sha256: str
    sandbox_candidate_interpreted: bool = True
    real_world_verified: bool = False
    permits_promotion: bool = False
    permits_external_action: bool = False


def _synthetic_difference(left: dict[str, Decimal],
                          right: dict[str, Decimal]) -> tuple[str, ...]:
    """Independent in-memory operator, no user paths or abstract code."""
    changed = []
    for name in sorted(left.keys() | right.keys()):
        if name not in left or name not in right or left[name] != right[name]:
            changed.append(name)
    return tuple(changed)


def _difference_digest(keys: tuple[str, ...]) -> str:
    return hashlib.sha256(canonical_bytes({
        "schema": "eai.synthetic.mismatch.keys.v1",
        "keys": list(keys),
    })).hexdigest()


def interpret_synthetic_candidate(
        store: AXNodeStore, problem: ProblemSpec,
        candidate: SynthesisCandidate,
        fixtures: tuple[SyntheticComparison, ...]
        ) -> SyntheticCandidateExecution:
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec or
            type(candidate) is not SynthesisCandidate or
            type(fixtures) is not tuple or not 2 <= len(fixtures) <= 12):
        raise ValueError("explicit bounded synthetic execution required")
    if problem.risk != "LOW" or "local.read" not in problem.permissions:
        raise ValueError("only explicitly scoped LOW-risk synthetic interpretation allowed")
    baseline = StructuralVerifier(store).check(problem, candidate)
    if baseline.status != "STRUCTURE_ONLY_UNVERIFIED":
        raise ValueError("structural candidate recheck rejected")
    steps = []
    for i, digest in enumerate(candidate.node_hashes):
        node = store.get(digest).as_dict()
        if ("csv_ref" not in node["signature"]["inputs"].values() or
                node["signature"]["output"] != "difference_receipt" or
                (i > 0 and "difference_receipt" not in
                 node["signature"]["inputs"].values()) or
                "local.read" not in node["capabilities"] or
                len(node["steps"]) != 1 or
                node["steps"][0]["skill"] != "csv.reconcile.v1"):
            # Intentionally no simulation of evidence.verify_receipt.v1:
            # evidence verification cannot be self-certified by an interpreter.
            raise ValueError("unimplemented or unsafe synthetic operator")
        steps.append(SyntheticStepWitness(digest, "difference_receipt", i))
    if len(steps) > problem.budget[0]:
        raise ValueError("step budget exceeded")
    families, seen = [], set()
    for fixture in fixtures:
        if type(fixture) is not SyntheticComparison or (
                type(fixture.family) is not str or
                not _ID.fullmatch(fixture.family) or
                fixture.family in seen):
            raise ValueError("duplicate or unsafe synthetic family")
        seen.add(fixture.family)
        left, right = _records(fixture.left), _records(fixture.right)
        # Execute EACH approved candidate step, feeding the typed
        # difference_receipt from its predecessor to its successor.
        receipt = None
        for step in steps:
            actual = _synthetic_difference(left, right)
            if receipt is not None and actual != receipt:
                raise ValueError("synthetic typed postcondition violated")
            receipt = actual
        assert receipt is not None  # structural chain has >=2 steps
        families.append(SyntheticFamilyWitness(
            fixture.family, _difference_digest(receipt), len(receipt), len(steps)))
    serialized = {
        "schema": "eai.synthetic.candidate.execution.v1",
        "problem_sha256": problem.digest(),
        "candidate_sha256": candidate.candidate_sha256,
        "steps": [[item.node_sha256, item.output_type, item.step_index]
                  for item in steps],
        "families": [[item.family, item.difference_sha256,
                      item.difference_count, item.executed_steps]
                     for item in families],
    }
    return SyntheticCandidateExecution(
        problem.digest(), candidate.candidate_sha256,
        "SYNTHETIC_INTERPRETED_UNVERIFIED",
        tuple(steps), tuple(families),
        hashlib.sha256(canonical_bytes(serialized)).hexdigest())
