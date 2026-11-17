"""C18 deterministic, synthetic-only curriculum; independent family split.

No source files, customer rows, provider data, random seeds or executable code
are consumed. Fixture agreement is NOT a verified real-world outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .contracts import canonical_bytes
from .logic_oracle import SyntheticComparison
from .synthetic_holdout import _fixture_hash


@dataclass(frozen=True)
class SyntheticCurriculum:
    seed: int
    train: tuple[SyntheticComparison, ...]
    heldout: tuple[SyntheticComparison, ...]
    manifest_sha256: str
    trust: str = "SYNTHETIC_FIXTURES_NOT_REAL_WORLD_EVIDENCE"


def generate_synthetic_curriculum(seed: int = 0) -> SyntheticCurriculum:
    """Exactly four disjoint, repeatable numeric reconciliation families."""
    if type(seed) is not int or not 0 <= seed <= 10000:
        raise ValueError("bounded nonprivate integer seed required")
    n = 100 + seed * 13
    train = (
        SyntheticComparison(
            f"train.equal.{seed}", (("a", f"{n}.00"),),
            (("a", str(n)),), ()),
        SyntheticComparison(
            f"train.changed.{seed}", (("b", str(n + 1)),),
            (("b", str(n + 3)),), ("b",)),
    )
    heldout = (
        SyntheticComparison(
            f"heldout.missing.{seed}",
            (("c", str(n + 5)), ("d", str(n + 6))),
            (("c", str(n + 5)), ("e", str(n + 6))),
            ("d", "e")),
        SyntheticComparison(
            f"heldout.equal.{seed}", (("h", f"{n + 9}.000"),),
            (("h", str(n + 9)),), ()),
    )
    fixtures = train + heldout
    if (len({item.family for item in fixtures}) != len(fixtures)
            or len({_fixture_hash(item) for item in fixtures}) != len(fixtures)):
        raise ValueError("synthetic curriculum family leakage")
    manifest_hash = hashlib.sha256(canonical_bytes({
        "schema": "eai.synthetic.curriculum.v1", "seed": seed,
        "fixtures": [
            {"family": f.family, "left": [list(x) for x in f.left],
             "right": [list(x) for x in f.right],
             "claimed_different": list(f.claimed_different)}
            for f in fixtures
        ],
    })).hexdigest()
    return SyntheticCurriculum(seed, train, heldout, manifest_hash)



def schedule_next_synthetic_cases(coverage_counts: dict[str, int], *,
                                  seed: int = 0, limit: int = 2):
    """Public offline caller that builds a bounded curriculum then ranks gaps."""
    from .curriculum_scheduler import select_curriculum_gaps
    return select_curriculum_gaps(
        generate_synthetic_curriculum(seed), coverage_counts, limit=limit)
