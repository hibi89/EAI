"""Pure synthetic CSV-key equality oracle for checking *claimed* effects.

This is NOT execution of AXNODE skills. Agreement on synthetic fixtures is
not evidence that the candidate implementation is correct, promoted, or safe.
Reference checks are EAI-owned finite Decimal computations, no model/network.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from .contracts import ProblemSpec
from .logic_synthesis import SynthesisCandidate
from .logic_verifier import StructuralVerifier

_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_DEC = re.compile(r"-?(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?\Z")
_MAX_ROWS = 24
_MAX_FIXTURES = 12


def _value(text: str) -> Decimal:
    if type(text) is not str or not _DEC.fullmatch(text):
        raise ValueError("bounded finite decimal required")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc


def _records(raw: tuple[tuple[str, str], ...]) -> dict[str, Decimal]:
    if type(raw) is not tuple or not 1 <= len(raw) <= _MAX_ROWS:
        raise ValueError("bounded synthetic rows required")
    result = {}
    for pair in raw:
        if type(pair) is not tuple or len(pair) != 2:
            raise ValueError("synthetic row tuple required")
        key, number = pair
        if type(key) is not str or not _ID.fullmatch(key) or key in result:
            raise ValueError("duplicate or untrusted synthetic key")
        result[key] = _value(number)
    return result


@dataclass(frozen=True)
class SyntheticComparison:
    """Untrusted claim of differing keyed rows, no source file or action."""
    family: str
    left: tuple[tuple[str, str], ...]
    right: tuple[tuple[str, str], ...]
    claimed_different: tuple[str, ...]


@dataclass(frozen=True)
class OracleAudit:
    status: str
    cases: tuple[tuple[str, str], ...]
    counterexamples: tuple[str, ...]
    independent_fixture_math: bool
    candidate_executed: bool = False
    semantic_verified: bool = False
    grants_promotion: bool = False


class SyntheticReconciliationOracle:
    """Independently recompute expected mismatch sets for supplied public fixtures."""

    def __init__(self, verifier: StructuralVerifier):
        if type(verifier) is not StructuralVerifier:
            raise ValueError("explicit independent structural verifier required")
        self.verifier = verifier

    def check(self, problem: ProblemSpec, candidate: SynthesisCandidate,
              fixtures: tuple[SyntheticComparison, ...]) -> OracleAudit:
        if type(problem) is not ProblemSpec or type(candidate) is not SynthesisCandidate:
            raise ValueError("typed problem/candidate required")
        if type(fixtures) is not tuple or not 2 <= len(fixtures) <= _MAX_FIXTURES:
            raise ValueError("two to twelve synthetic fixture claims required")
        if problem.risk == "HIGH":
            return OracleAudit("HIGH_RISK_BLOCKED", (), (), False)
        receipt = self.verifier.check(problem, candidate)
        if receipt.status != "STRUCTURE_ONLY_UNVERIFIED":
            return OracleAudit("STRUCTURAL_BASELINE_REJECTED", (), (), False)
        observed = []
        wrong = []
        families = set()
        for fx in fixtures:
            if type(fx) is not SyntheticComparison:
                raise ValueError("typed synthetic fixture required")
            if type(fx.family) is not str or not _ID.fullmatch(fx.family) or fx.family in families:
                raise ValueError("unique bounded fixture family required")
            families.add(fx.family)
            lhs, rhs = _records(fx.left), _records(fx.right)
            if type(fx.claimed_different) is not tuple or len(fx.claimed_different) > _MAX_ROWS * 2:
                raise ValueError("bounded claimed difference set required")
            if any(type(key) is not str or not _ID.fullmatch(key) for key in fx.claimed_different):
                raise ValueError("invalid claimed key")
            if tuple(sorted(set(fx.claimed_different))) != fx.claimed_different:
                raise ValueError("sorted unique mismatch claims required")
            reference = tuple(sorted(
                key for key in lhs.keys() | rhs.keys()
                if key not in lhs or key not in rhs or lhs[key] != rhs[key]
            ))
            state = "SYNTHETIC_CLAIM_AGREES" if fx.claimed_different == reference else "SYNTHETIC_CLAIM_CONTRADICTED"
            observed.append((fx.family, state))
            if state == "SYNTHETIC_CLAIM_CONTRADICTED":
                wrong.append(fx.family)
        return OracleAudit(
            "SYNTHETIC_COUNTEREXAMPLE_FOUND" if wrong else
            "SYNTHETIC_CLAIMS_MATCH_UNVERIFIED",
            tuple(observed), tuple(wrong), True,
        )
