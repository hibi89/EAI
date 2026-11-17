"""Run existing CPU reconciliation ONLY on disposable synthetic fixture CSV.

An independent Decimal reference checks the actual CPU solver's returned
status, counts and discrepancy keys. This is baseline regression evidence,
NOT execution/verification/promotion of a composed AXNODE candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec
from .logic_synthesis import SynthesisCandidate
from .logic_oracle import SyntheticComparison, _records
from .logic_validation_pipeline import review_synthesis_candidate
from .reconcile_csv import reconcile_csv


@dataclass(frozen=True)
class CPUSolverFixtureResult:
    family: str
    verdict: str
    expected_status: str
    actual_status: str
    baseline_executed: bool
    composed_candidate_executed: bool = False


@dataclass(frozen=True)
class ActualSolverAudit:
    disposition: str
    structural_synthetic_review: str
    results: tuple[CPUSolverFixtureResult, ...]
    baseline_cpu_executed: bool
    composed_candidate_executed: bool = False
    semantic_verified: bool = False
    permits_promotion: bool = False


def _expected(left: dict[str, Decimal], right: dict[str, Decimal]):
    counts = {"agree": 0, "different": 0, "left_only": 0,
              "right_only": 0, "non_numeric": 0}
    details = []
    for key in sorted(left.keys() | right.keys()):
        if key not in left:
            kind = "RIGHT_ONLY"
            counts["right_only"] += 1
        elif key not in right:
            kind = "LEFT_ONLY"
            counts["left_only"] += 1
        elif left[key] != right[key]:
            kind = "DIFFERENT"
            counts["different"] += 1
        else:
            counts["agree"] += 1
            continue
        details.append((kind, key))
    status = "CONFLICT" if details else "AGREE"
    return status, counts, tuple(details)


def _write_synthetic_csv(path: Path, rows: tuple[tuple[str, str], ...]):
    # Rows are validated by _records before writing to the disposable folder.
    with path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["key", "value"])
        writer.writerows(rows)


def compare_real_cpu_on_synthetic(
        fixtures: tuple[SyntheticComparison, ...]
        ) -> tuple[CPUSolverFixtureResult, ...]:
    """Run only existing read-only reconcile_csv against owned tiny files."""
    if type(fixtures) is not tuple or not 2 <= len(fixtures) <= 12:
        raise ValueError("two to twelve synthetic fixtures required")
    families = set()
    results = []
    for item in fixtures:
        if type(item) is not SyntheticComparison:
            raise ValueError("typed synthetic fixture required")
        if (type(item.family) is not str or len(item.family) > 64 or
                item.family in families):
            raise ValueError("duplicate or invalid synthetic family")
        families.add(item.family)
        left, right = _records(item.left), _records(item.right)
        expected_status, expected_counts, expected_details = _expected(left, right)
        if len(expected_details) > 20:
            results.append(CPUSolverFixtureResult(
                item.family, "INCONCLUSIVE_TOO_MANY_DETAILS",
                expected_status, "NOT_RUN", False))
            continue
        with tempfile.TemporaryDirectory(prefix="eai-cpu-synthetic-") as tmp:
            a, b = Path(tmp) / "left.csv", Path(tmp) / "right.csv"
            _write_synthetic_csv(a, item.left)
            _write_synthetic_csv(b, item.right)
            if a.read_bytes() == b.read_bytes():
                results.append(CPUSolverFixtureResult(
                    item.family, "INCONCLUSIVE_IDENTICAL_SOURCE_BYTES",
                    expected_status, "NOT_RUN", False))
                continue
            try:
                actual = reconcile_csv(a, b, key="key", value="value",
                                       tolerance="0", encoding="utf-8")
            except (ValueError, OSError, UnicodeError, csv.Error):
                results.append(CPUSolverFixtureResult(
                    item.family, "BASELINE_CPU_EXCEPTION",
                    expected_status, "ERROR", True))
                continue
            reported = actual.get("status", "MALFORMED")
            reported_counts = actual.get("counts")
            reported_details = actual.get("differences")
            source_hashes = actual.get("sources")
            valid_hashes = (
                type(source_hashes) is list and len(source_hashes) == 2 and
                all(type(rec) is dict for rec in source_hashes) and
                source_hashes[0].get("sha256") == hashlib.sha256(a.read_bytes()).hexdigest() and
                source_hashes[1].get("sha256") == hashlib.sha256(b.read_bytes()).hexdigest()
            )
            valid_details = (
                type(reported_details) is list and
                tuple((e.get("kind"), e.get("key")) for e in reported_details
                      if type(e) is dict) == expected_details and
                len(reported_details) == len(expected_details) and
                actual.get("truncated") == 0
            )
            agree = (reported == expected_status and
                     reported_counts == expected_counts and
                     valid_details and valid_hashes)
            results.append(CPUSolverFixtureResult(
                item.family,
                "BASELINE_CPU_MATCH_UNVERIFIED" if agree else "BASELINE_CPU_MISMATCH",
                expected_status, str(reported)[:32], True))
    return tuple(results)


def review_candidate_with_cpu_baseline(
        store: AXNodeStore, problem: ProblemSpec,
        candidate: SynthesisCandidate,
        fixtures: tuple[SyntheticComparison, ...]) -> ActualSolverAudit:
    """No candidate execution; actual existing CPU baseline only after structure."""
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec or
            type(candidate) is not SynthesisCandidate or type(fixtures) is not tuple):
        raise ValueError("typed bounded review required")
    structural = review_synthesis_candidate(store, problem, candidate, fixtures)
    if structural.disposition != "SYNTHETIC_EVIDENCE_ONLY_NOT_PROMOTED":
        return ActualSolverAudit("HOLD_STRUCTURAL_OR_SYNTHETIC_CLAIM",
                                 structural.disposition, (), False)
    checked = compare_real_cpu_on_synthetic(fixtures)
    if all(item.verdict == "BASELINE_CPU_MATCH_UNVERIFIED" for item in checked):
        decision = "CPU_BASELINE_MATCHES_CANDIDATE_STILL_UNVERIFIED"
    else:
        decision = "HOLD_CPU_BASELINE_MISMATCH_OR_INCONCLUSIVE"
    return ActualSolverAudit(
        decision, structural.disposition, checked,
        any(item.baseline_executed for item in checked))
