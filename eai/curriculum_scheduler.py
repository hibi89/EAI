"""C18 deterministic CPU curriculum next-case selection from owned gap counts."""
from __future__ import annotations

from dataclasses import dataclass

from .synthetic_curriculum import SyntheticCurriculum
from .contracts import canonical_sha256


@dataclass(frozen=True)
class CurriculumSelection:
    status: str
    source_manifest_sha256: str
    selection_sha256: str
    cases: tuple
    coverage_counts: tuple[tuple[str, int], ...]
    trust: str = "SYNTHETIC_ONLY_NOT_VERIFIED_LEARNING"


def select_curriculum_gaps(
    curriculum: SyntheticCurriculum, coverage_counts: dict[str, int], *,
    limit: int = 2
) -> CurriculumSelection:
    if (type(curriculum) is not SyntheticCurriculum
            or type(coverage_counts) is not dict
            or type(limit) is not int or not 1 <= limit <= 2
            or len(coverage_counts) > 8):
        raise ValueError("bounded local curriculum selection required")
    known = {case.family for case in curriculum.train}
    if (len(known) != len(curriculum.train)
            or any(type(key) is not str or key not in known
                   or type(value) is not int or not 0 <= value <= 100000
                   for key, value in coverage_counts.items())):
        raise ValueError("unknown or unbounded training coverage")
    # Training cases only. Heldout/test cases may never be selected as training.
    selected = tuple(sorted(curriculum.train,
                            key=lambda case: (coverage_counts.get(case.family, 0),
                                              case.family))[:limit])
    counts = tuple(sorted(coverage_counts.items()))
    proof = canonical_sha256({
        "schema": "eai.synthetic.curriculum.selection.v1",
        "manifest": curriculum.manifest_sha256,
        "selected_families": [c.family for c in selected],
        "coverage": [list(v) for v in counts],
    })
    return CurriculumSelection("SYNTHETIC_GAP_ORDER_ONLY",
                               curriculum.manifest_sha256, proof, selected,
                               counts)
