"""SWU-039 isolated Hydrogen proposal codec; no live API or outbound transport.

These pure functions construct a REVIEW-ONLY draft and quarantine a previously
obtained response. They do not prove provider provenance, ownership, free-tier
entitlement, human outbound approval, or the truth of a model's ideas. Never
connect this codec directly to a socket or promote its suggestions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .contracts import canonical_bytes, strict_json
from .hydrogen_packet import ResearchPacket
from .research_policy import ResearchMode
from .research_providers import ResearchCoordinator

_MODEL = "gemini-4-hydrogen"
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_MAX_RESPONSE_BYTES = 16 * 1024
_MAX_TEXT_BYTES = 8 * 1024


@dataclass(frozen=True)
class DraftHydrogenRequest:
    request_sha256: str
    model: str
    payload_sha256: str
    payload: bytes
    status: str = "LOCAL_PREVIEW_ONLY_NO_REMOTE_CONSENT"
    sends_allowed: bool = False


@dataclass(frozen=True)
class UntrustedHydrogenIdea:
    idea_id: str
    task_family: str
    summary: str
    counterexamples: tuple[str, ...]
    assumptions: tuple[str, ...]
    response_sha256: str
    provenance: str = "REMOTE_CLAIM_UNVERIFIED"
    permits_execution: bool = False
    permits_training: bool = False
    permits_promotion: bool = False


@dataclass(frozen=True)
class HydrogenTranscriptReview:
    baseline: object
    disposition: str
    request_sha256: str
    ideas: tuple[UntrustedHydrogenIdea, ...] = ()
    reason: str = ""
    provider_called_by_eai: bool = False
    external_bytes_sent_by_eai: int = 0
    trusted_for_training: bool = False
    permits_execution: bool = False
    permits_promotion: bool = False


def _packet(packet: ResearchPacket) -> ResearchPacket:
    if type(packet) is not ResearchPacket:
        raise ValueError("typed synthetic/public research packet required")
    # Direct dataclass construction does not validate its fields.
    return ResearchPacket.from_json(packet.to_json_bytes())


def _short_text(value: object, *, max_len: int = 500) -> str:
    if (type(value) is not str or not 1 <= len(value) <= max_len
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("invalid bounded untrusted proposal text")
    return value


def _terms(value: object) -> tuple[str, ...]:
    if type(value) is not list or len(value) > 4:
        raise ValueError("invalid proposal term inventory")
    return tuple(_short_text(v, max_len=180) for v in value)


def build_hydrogen_request_preview(packet: ResearchPacket) -> DraftHydrogenRequest:
    """Build exact public/synthetic HTTP BODY bytes; does not perform HTTP.

    This is an auditable payload draft, NOT a human approval, service request,
    authenticated free-tier entitlement or enabled provider configuration.
    """
    checked = _packet(packet)
    instructions = (
        "Provide up to two untrusted synthetic counterexample hypotheses only. "
        "Do not provide executable code, tool requests, facts, or final decisions. "
        "Return one JSON object with exact keys schema, request_sha256, "
        "task_family, hypotheses. Each hypothesis has exact keys idea_id, "
        "summary, counterexamples, assumptions. Do not echo private data. "
        "Schema: eai.hydrogen.candidate.idea.v1."
    )
    payload = canonical_bytes({
        "contents": [{"role": "user", "parts": [{"text":
            instructions + "\nSynthetic research packet:\n" +
            checked.review_exact_outbound_text()}]}],
        "generationConfig": {
            "candidateCount": 1,
            "maxOutputTokens": 512,
            "responseMimeType": "application/json",
            "temperature": 0,
        },
    })
    return DraftHydrogenRequest(
        checked.request_sha256(), _MODEL,
        hashlib.sha256(payload).hexdigest(), payload)


def review_hydrogen_response(
    packet: ResearchPacket, baseline: object, response: str | bytes,
    *, coordinator: ResearchCoordinator,
) -> HydrogenTranscriptReview:
    """Strictly local, untrusted response inspection; always preserves OFF result.

    The caller supplies response bytes, which may be forged. This function
    DOES NOT prove the server actually produced them, or confer authority.
    Even when a legacy policy exposes permissive booleans, no live send occurs.
    """
    checked = _packet(packet)
    if type(coordinator) is not ResearchCoordinator:
        raise ValueError("typed EAI coordinator required")
    sha = checked.request_sha256()
    if coordinator.policy.mode is ResearchMode.OFF:
        return HydrogenTranscriptReview(baseline, "OFF", sha)
    if not coordinator.policy.allows_remote_proposal():
        return HydrogenTranscriptReview(
            baseline, "HOLD_PROVIDER_CONSENT_OR_FREE_TIER", sha)
    # The policy booleans alone do not prove actual owner approval. The method
    # remains a local transcript parser, and results are NEVER trusted.
    if type(response) not in (str, bytes):
        raise ValueError("bounded response text/bytes required")
    try:
        doc = strict_json(response, max_bytes=_MAX_RESPONSE_BYTES)
        candidates = doc.get("candidates")
        if type(candidates) is not list or len(candidates) != 1:
            raise ValueError("single bounded Hydrogen candidate required")
        candidate = candidates[0]
        if (type(candidate) is not dict or candidate.get("finishReason") != "STOP"):
            raise ValueError("nonfinal or unsafe Hydrogen candidate")
        content = candidate.get("content")
        if (type(content) is not dict or content.get("role") != "model"):
            raise ValueError("unrecognized model response content")
        parts = content.get("parts")
        if (type(parts) is not list or len(parts) != 1
                or type(parts[0]) is not dict or set(parts[0]) != {"text"}
                or type(parts[0]["text"]) is not str):
            raise ValueError("non-text or tool-enabled response blocked")
        text = parts[0]["text"]
        data = strict_json(text, max_bytes=_MAX_TEXT_BYTES)
        if (set(data) != {"schema", "request_sha256", "task_family", "hypotheses"}
                or data["schema"] != "eai.hydrogen.candidate.idea.v1"
                or data["request_sha256"] != sha
                or data["task_family"] != checked.task_family):
            raise ValueError("Hydrogen response not bound to requested packet")
        raw_ideas = data["hypotheses"]
        if type(raw_ideas) is not list or not 1 <= len(raw_ideas) <= 2:
            raise ValueError("bounded Hydrogen hypothesis list required")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        ideas = []
        used = set()
        for raw in raw_ideas:
            if (type(raw) is not dict or set(raw) != {
                    "idea_id", "summary", "counterexamples", "assumptions"}):
                raise ValueError("unknown or missing proposal fields")
            idea_id = raw["idea_id"]
            if (type(idea_id) is not str or not _ID.fullmatch(idea_id)
                    or idea_id in used):
                raise ValueError("invalid or duplicated idea identifier")
            used.add(idea_id)
            ideas.append(UntrustedHydrogenIdea(
                idea_id, checked.task_family,
                _short_text(raw["summary"]),
                _terms(raw["counterexamples"]),
                _terms(raw["assumptions"]), digest))
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
        return HydrogenTranscriptReview(
            baseline, "HOLD_INVALID_UNTRUSTED_RESPONSE", sha,
            reason="RESPONSE_OR_PROPOSAL_CONTRACT_REJECTED")
    return HydrogenTranscriptReview(
        baseline, "LOCAL_UNTRUSTED_IDEAS_REVIEW_ONLY", sha,
        tuple(ideas), "NO_REMOTE_PROVENANCE_OR_SEMANTIC_TRUTH")
