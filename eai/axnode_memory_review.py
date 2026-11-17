"""Read-only, fail-closed AXNODE memory reuse advisory.

No observed episode is a verified outcome. A negative example sharing the
same abstract label pauses positive/procedural reuse; parent withdrawal never
silently authorizes descendants.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .axnode_memory import AXNodeMemory
from .contracts import canonical_bytes


@dataclass(frozen=True)
class MemoryReuseReview:
    label: str
    anchor_sha256: str
    memory_sha256: str
    tier: str
    disposition: str
    authority: str = "NONE_UNVERIFIED"


def review_memory_reuse(memory: AXNodeMemory, query: str, *,
                        withdrawn_hashes: tuple[str, ...] = (),
                        now: int | None = None,
                        limit: int = 12) -> tuple[MemoryReuseReview, ...]:
    if type(memory) is not AXNodeMemory:
        raise ValueError("explicit local memory index required")
    if (type(withdrawn_hashes) is not tuple or len(withdrawn_hashes) > 32
            or len(set(withdrawn_hashes)) != len(withdrawn_hashes)):
        raise ValueError("bounded withdrawn AXNODE references required")
    for digest in withdrawn_hashes:
        # Validates the content address without altering graph/status.
        memory.store.get(digest)
    entries = memory.find(query, now=now, limit=limit)
    # A negative record must not be hidden merely because ranking truncated
    # the visible result set. Read only matching labels and verify hashes via
    # memory.get(); bounded by the existing local 3000-record scan budget.
    labels = sorted({item["label"] for item in entries})
    labels_with_negative = set()
    if labels:
        marks = ",".join("?" for _ in labels)
        rows = memory.db.execute(
            "SELECT sha256 FROM entries WHERE label IN (" + marks +
            ") ORDER BY sha256 LIMIT 3001", labels).fetchall()
        if len(rows) > 3000:
            raise ValueError("negative memory coverage exceeds safe review budget")
        for (digest,) in rows:
            item = memory.get(digest)
            if item["tier"] == "NEGATIVE" or item["outcome"] == "FAILURE_OBSERVED":
                labels_with_negative.add(item["label"])
    withdrawn = set(withdrawn_hashes)
    reports = []
    for item in entries:
        anchor = item["anchor_sha"]
        observed = set()
        todo = [anchor]
        invalid_lineage = False
        while todo:
            digest = todo.pop()
            if digest in observed:
                continue
            observed.add(digest)
            if len(observed) > 3000:
                raise ValueError("lineage review budget exhausted")
            if digest in withdrawn:
                invalid_lineage = True
            # Parent pointers are advisory but content must still be present.
            memory.store.get(digest)
            todo.extend(memory.store.parents_of(digest))
        if invalid_lineage:
            decision = "REVIEW_WITHDRAWN_PARENT"
        elif item["tier"] == "NEGATIVE" or item["outcome"] == "FAILURE_OBSERVED":
            decision = "REVIEW_NEGATIVE_OUTCOME"
        elif item["label"] in labels_with_negative:
            decision = "REVIEW_CONTRADICTED_BY_NEGATIVE_MEMORY"
        else:
            decision = "UNVERIFIED_CANDIDATE_ONLY"
        reports.append(MemoryReuseReview(
            item["label"], anchor,
            hashlib.sha256(canonical_bytes(item)).hexdigest(),
            item["tier"], decision,
        ))
    return tuple(reports)
