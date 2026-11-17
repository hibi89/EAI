"""Leak-aware B0 synthetic held-out baseline, without pretending B1/B2 uplift.

Only existing CPU reconcile implementation is executed against temporary
synthetic fixtures. The newly composed AXNODE is *not* run or trained; no
private episodes/fixtures are persisted and no model/provider is called.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .logic_oracle import _ID, _records

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec, canonical_bytes
from .logic_oracle import SyntheticComparison
from .logic_synthesis import SynthesisCandidate
from .solver_reference_check import review_candidate_with_cpu_baseline


@dataclass(frozen=True)
class B0HeldoutReport:
    status: str
    training_families: tuple[str, ...]
    heldout_families: tuple[str, ...]
    training_cpu_matches: int
    heldout_cpu_matches: int
    observed_b0_cases: int
    candidate_b1_evaluated: bool = False
    candidate_b2_evaluated: bool = False
    verified_uplift: str = "NOT_MEASURED"
    supports_activation: bool = False


def _fixture_hash(fixture: SyntheticComparison) -> str:
    # Data leakage is semantic, not a textual SHA match. Reordering rows,
    # changing numeric formatting or swapping two sources cannot disguise
    # an identical heldout comparison as a new test family.
    def normalized(rows):
        values = _records(rows)
        return [[key, "0" if value == 0 else format(value.normalize(), "f")]
                for key, value in sorted(values.items())]
    sides = sorted([
        hashlib.sha256(canonical_bytes({
            "schema": "eai.synthetic.fixture.normalized_rows.v1",
            "rows": normalized(fixture.left),
        })).hexdigest(),
        hashlib.sha256(canonical_bytes({
            "schema": "eai.synthetic.fixture.normalized_rows.v1",
            "rows": normalized(fixture.right),
        })).hexdigest(),
    ])
    return hashlib.sha256(canonical_bytes({"unordered_source_hashes": sides})).hexdigest()


def compare_b0_train_and_heldout(
        store: AXNodeStore, problem: ProblemSpec,
        candidate: SynthesisCandidate,
        train: tuple[SyntheticComparison, ...],
        heldout: tuple[SyntheticComparison, ...]) -> B0HeldoutReport:
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec or
            type(candidate) is not SynthesisCandidate or
            type(train) is not tuple or type(heldout) is not tuple or
            not 2 <= len(train) <= 12 or not 2 <= len(heldout) <= 12):
        raise ValueError("two to twelve independent train and heldout fixtures required")
    if (any(type(f) is not SyntheticComparison or
            type(f.family) is not str or not _ID.fullmatch(f.family)
            for f in train+heldout) or
            len({f.family for f in train+heldout}) != len(train+heldout) or
            len({_fixture_hash(f) for f in train+heldout}) != len(train+heldout)):
        raise ValueError("duplicate family or leaked synthetic fixture across split")
    # Re-evaluation is mandatory on BOTH splits. A forged train result is not
    # allowed to become a valid heldout result through comparison/training.
    training = review_candidate_with_cpu_baseline(
        store, problem, candidate, train)
    if training.disposition != "CPU_BASELINE_MATCHES_CANDIDATE_STILL_UNVERIFIED":
        return B0HeldoutReport(
            "HOLD_B0_TRAINING_FAILURE", tuple(f.family for f in train),
            tuple(f.family for f in heldout),
            sum(f.verdict == "BASELINE_CPU_MATCH_UNVERIFIED"
                for f in training.results), 0, len(training.results))
    testing = review_candidate_with_cpu_baseline(
        store, problem, candidate, heldout)
    train_matches = sum(f.verdict == "BASELINE_CPU_MATCH_UNVERIFIED"
                        for f in training.results)
    test_matches = sum(f.verdict == "BASELINE_CPU_MATCH_UNVERIFIED"
                       for f in testing.results)
    status = ("B0_SYNTHETIC_HELDOUT_MATCH_UNVERIFIED" if
              testing.disposition ==
              "CPU_BASELINE_MATCHES_CANDIDATE_STILL_UNVERIFIED" and
              test_matches == len(heldout)
              else "HOLD_B0_HELDOUT_FAILURE")
    return B0HeldoutReport(
        status, tuple(f.family for f in train),
        tuple(f.family for f in heldout),
        train_matches, test_matches,
        len(training.results)+len(testing.results))
