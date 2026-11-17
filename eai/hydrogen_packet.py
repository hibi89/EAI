"""Synthetic/public-only *proposal preview* contract. Never sends a request.

External visibility requires a separate signed per-send approval and verified
free API entitlement through the dormant REST adapter. The regex guards only
obvious leakage patterns, NOT sensitive-data classification assurance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .contracts import canonical_bytes, strict_json

_TASKS = frozenset({
    "synthetic.math", "synthetic.csv", "synthetic.scheduling",
    "synthetic.planning", "public.algorithm"
})
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_NONCE = re.compile(r"[a-zA-Z0-9_-]{8,40}\Z")
_UNSAFE = re.compile(
    r"(?i)(?:https?://|www\.|[a-z0-9_.+-]+@[a-z0-9.-]+\.[a-z]{2,}|"
    r"[A-Z]:\\|/home/|/Users/|\.env\b|api[_-]?key\b|password\b|"
    r"bearer\s+|-----BEGIN |private[_ -]?key\b)"
)
_MAX_PACKET_BYTES = 3 * 1024


@dataclass(frozen=True)
class ResearchPacket:
    """Untrusted model provider sees only an independently approved abstract."""
    nonce: str
    task_family: str
    abstract: str
    strategy_ids: tuple[str, ...]
    objectives: tuple[str, ...]
    version: int = 1
    visibility: str = "PUBLIC_SYNTHETIC_ONLY"

    @classmethod
    def validate(cls, raw: dict) -> "ResearchPacket":
        if type(raw) is not dict or set(raw) != {
            "version","nonce","task_family","visibility","abstract",
            "strategy_ids","objectives"
        }:
            raise ValueError("unknown or missing research packet field")
        if type(raw["version"]) is not int or raw["version"] != 1:
            raise ValueError("unsupported research packet version")
        nonce, family = raw["nonce"], raw["task_family"]
        if (type(nonce) is not str or not _NONCE.fullmatch(nonce) or
                type(family) is not str or family not in _TASKS or
                type(raw["visibility"]) is not str or
                raw["visibility"] != "PUBLIC_SYNTHETIC_ONLY"):
            raise ValueError("research packet not approved for synthetic/public processing")
        abstract = raw["abstract"]
        if (type(abstract) is not str or not 1 <= len(abstract) <= 500
                or abstract != abstract.strip() or
                any(ord(ch) < 32 for ch in abstract) or _UNSAFE.search(abstract)):
            raise ValueError("unsafe research abstract, manual review required")
        ids, objectives = raw["strategy_ids"], raw["objectives"]
        if (type(ids) is not list or len(ids) > 8 or
                any(type(v) is not str or not _ID.fullmatch(v) for v in ids) or
                len(set(ids)) != len(ids)):
            raise ValueError("invalid public strategy IDs")
        if (type(objectives) is not list or not 1 <= len(objectives) <= 8 or
                any(type(v) is not str or not _ID.fullmatch(v) for v in objectives)
                or len(set(objectives)) != len(objectives)):
            raise ValueError("invalid validation objectives")
        if len(canonical_bytes(raw)) > _MAX_PACKET_BYTES:
            raise ValueError("research packet size exceeded")
        return cls(nonce, family, abstract, tuple(ids), tuple(objectives))

    @classmethod
    def from_json(cls, data: str | bytes) -> "ResearchPacket":
        return cls.validate(strict_json(data, max_bytes=_MAX_PACKET_BYTES))

    def to_json_bytes(self) -> bytes:
        raw = {
            "version": 1, "nonce": self.nonce, "task_family": self.task_family,
            "visibility": self.visibility, "abstract": self.abstract,
            "strategy_ids": list(self.strategy_ids), "objectives": list(self.objectives)
        }
        return canonical_bytes(raw)

    def request_sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


    def record_local_review(self, review_directory, *,
                            reviewed_preview_sha256: str,
                            reviewed: bool = False):
        """Persist only an exact local review; NEVER approve an external send."""
        from .research_consent import record_local_packet_review
        return record_local_packet_review(
            self, review_directory,
            reviewed_preview_sha256=reviewed_preview_sha256,
            reviewed=reviewed)

    def review_exact_outbound_text(self) -> str:
        """Human-only local preview; never called by a network transport."""
        return self.to_json_bytes().decode("utf-8")
