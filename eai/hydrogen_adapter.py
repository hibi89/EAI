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


# SWU-039: dormant REAL REST transport with exact, owner-signed, per-send proof.
# Merely setting ResearchPolicy booleans, recording a local preview, or using a
# mock approval is insufficient. This entrypoint is never called by the OFF
# coordinator. It does not obtain keys, create an owner trust root or enroll a
# Google project. The OWNER must separately verify their FREE-only account,
# inspect exact bytes, authorize each send and provision a signing public key.
# A human attestation cannot independently guarantee Google's billing tier.

@dataclass(frozen=True)
class SignedLiveSendPermit:
    """Externally provisioned owner statement; not a self-authorizing flag."""
    statement: bytes
    signature: bytes
    owner_public_key: bytes
    trusted_owner_key_sha256: str


@dataclass(frozen=True)
class LiveHydrogenResult:
    """Untrusted ideas can never affect the EAI CPU baseline."""
    baseline: object
    status: str
    request_sha256: str
    ideas: tuple[UntrustedHydrogenIdea, ...] = ()
    reason: str = ""
    requests_attempted: int = 0
    externally_verified: bool = False
    permits_execution: bool = False
    permits_training: bool = False
    permits_promotion: bool = False


_LIVE_HOST = "generativelanguage.googleapis.com"
_LIVE_PATH = "/v1beta/models/gemini-4-hydrogen:generateContent"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_NONCE_LIVE = re.compile(r"[A-Za-z0-9_-]{20,64}\Z")
_PROJECT = re.compile(r"[a-z][a-z0-9-]{5,62}\Z")
_KEY = re.compile(r"[A-Za-z0-9_-]{20,256}\Z")
_LIVE_SCHEMA = "eai.hydrogen.owner.send.v1"
_LIVE_LEDGER_VERSION = 1
_LIVE_MAX_INPUT_TOKENS = 512
_LIVE_MAX_OUTPUT_TOKENS = 512
_LIVE_MAX_RPM = 2
_LIVE_MAX_RPD = 5
_LIVE_MAX_TPM = 2048


def _check_live_owner_permit(
    permit: SignedLiveSendPermit, packet: ResearchPacket,
    draft: DraftHydrogenRequest, api_key: str, now: int,
) -> tuple[str, str, str]:
    """Require a genuine detached owner signature over an exact single send.

    The separately pinned key must come from an owner-controlled local trust
    process. This proves key possession, not Google's actual tier or identity.
    """
    if (type(permit) is not SignedLiveSendPermit
            or type(permit.statement) is not bytes
            or type(permit.signature) is not bytes
            or len(permit.signature) != 64
            or type(permit.owner_public_key) is not bytes
            or len(permit.owner_public_key) != 32
            or type(permit.trusted_owner_key_sha256) is not str
            or not _SHA256.fullmatch(permit.trusted_owner_key_sha256)
            or hashlib.sha256(permit.owner_public_key).hexdigest()
            != permit.trusted_owner_key_sha256):
        raise PermissionError("missing or invalid externally pinned owner authority")
    raw = strict_json(permit.statement, max_bytes=2048)
    expected = {
        "schema", "model", "request_sha256", "payload_sha256",
        "api_key_sha256", "project_id", "nonce", "issued_at",
        "expires_at", "free_tier_checked_at", "free_tier_attestation",
        "paid_budget_usd", "per_send",
    }
    if (set(raw) != expected or raw["schema"] != _LIVE_SCHEMA
            or raw["model"] != _MODEL or raw["per_send"] is not True
            or type(raw["paid_budget_usd"]) is not int
            or raw["paid_budget_usd"] != 0
            or type(raw["request_sha256"]) is not str
            or raw["request_sha256"] != packet.request_sha256()
            or type(raw["payload_sha256"]) is not str
            or raw["payload_sha256"] != draft.payload_sha256
            or type(raw["api_key_sha256"]) is not str
            or raw["api_key_sha256"] != hashlib.sha256(
                api_key.encode("ascii")).hexdigest()
            or type(raw["project_id"]) is not str
            or not _PROJECT.fullmatch(raw["project_id"])
            or type(raw["nonce"]) is not str
            or not _NONCE_LIVE.fullmatch(raw["nonce"])
            or raw["free_tier_attestation"] != "OWNER_REVIEWED_FREE_ONLY"
            or any(type(raw[k]) is not int for k in (
                "issued_at", "expires_at", "free_tier_checked_at"))
            or not now - 300 <= raw["issued_at"] <= now
            or not now < raw["expires_at"] <= raw["issued_at"] + 900
            or not now - 3600 <= raw["free_tier_checked_at"] <= now):
        raise PermissionError("owner send scope, free-tier attestation or expiry invalid")
    if permit.statement != canonical_bytes(raw):
        raise PermissionError("noncanonical owner approval")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(permit.owner_public_key).verify(
            permit.signature, permit.statement)
    except (ImportError, ValueError, TypeError) as exc:
        raise PermissionError("owner signature verifier unavailable") from exc
    except Exception as exc:
        raise PermissionError("owner send signature verification failed") from exc
    return raw["project_id"], raw["nonce"], permit.trusted_owner_key_sha256



def prepare_live_owner_statement(
    packet: ResearchPacket, *, api_key_sha256: str, project_id: str,
    nonce: str, issued_at: int, expires_at: int, free_tier_checked_at: int,
) -> bytes:
    """Prepare exact unsigned consent for external, owner-controlled signing.

    This function DOES NOT approve a send. The user must inspect the exact
    request preview and free-only project entitlement in their own account,
    then sign this statement outside EAI. Never place a private key in Git.
    """
    checked = _packet(packet)
    draft = build_hydrogen_request_preview(checked)
    if (type(api_key_sha256) is not str or not _SHA256.fullmatch(api_key_sha256)
            or type(project_id) is not str or not _PROJECT.fullmatch(project_id)
            or type(nonce) is not str or not _NONCE_LIVE.fullmatch(nonce)
            or any(type(x) is not int for x in (
                issued_at, expires_at, free_tier_checked_at))
            or not issued_at < expires_at <= issued_at + 900
            or not issued_at - 3600 <= free_tier_checked_at <= issued_at):
        raise ValueError("cannot prepare unscoped or expiring owner consent")
    return canonical_bytes({
        "schema": _LIVE_SCHEMA,
        "model": _MODEL,
        "request_sha256": checked.request_sha256(),
        "payload_sha256": draft.payload_sha256,
        "api_key_sha256": api_key_sha256,
        "project_id": project_id,
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "free_tier_checked_at": free_tier_checked_at,
        "free_tier_attestation": "OWNER_REVIEWED_FREE_ONLY",
        "paid_budget_usd": 0,
        "per_send": True,
    })


class _LiveSendLedger:
    """Private, durable single-project fail-closed quota, replay and breaker.

    This is NOT the existing mock-only research quota ledger. A real project
    must be configured to use ONE owner-controlled ledger across processes.
    """

    def __init__(self, path, *, project_id: str, owner_key_sha256: str,
                 allow_create: bool = False):
        from pathlib import Path
        import os
        import sqlite3
        p = Path(path).expanduser()
        if (type(allow_create) is not bool
                or p.suffix != ".sqlite"
                or p.is_symlink() or p.parent.is_symlink()
                or not p.parent.is_dir()
                or (p.exists() and not p.is_file())):
            raise PermissionError("explicit private isolated live ledger required")
        exists = p.exists()
        if not exists and not allow_create:
            raise PermissionError("live ledger cannot be created implicitly")
        if not exists:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(fd)
        self.db = sqlite3.connect(
            p.resolve(strict=True).as_uri() + "?mode=rw",
            uri=True, isolation_level=None, timeout=3)
        try:
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA busy_timeout=3000")
            ver = self.db.execute("PRAGMA user_version").fetchone()[0]
            if exists:
                if ver != _LIVE_LEDGER_VERSION:
                    raise PermissionError("unexpected live ledger version")
                names = {x[0] for x in self.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'")}
                if names != {"eai_live_control", "eai_live_reservations"}:
                    raise PermissionError("unexpected live ledger tables")
            else:
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    self.db.execute(
                        "CREATE TABLE eai_live_control("
                        "id INTEGER PRIMARY KEY CHECK(id=1), "
                        "project TEXT NOT NULL, owner_key TEXT NOT NULL, "
                        "state TEXT NOT NULL CHECK(state IN ('READY','HOLD')))")
                    self.db.execute(
                        "CREATE TABLE eai_live_reservations("
                        "nonce TEXT PRIMARY KEY, utc INTEGER NOT NULL, "
                        "tokens INTEGER NOT NULL, status TEXT NOT NULL)")
                    self.db.execute(
                        "INSERT INTO eai_live_control VALUES(1,?,?, 'READY')",
                        (project_id, owner_key_sha256))
                    self.db.execute("PRAGMA user_version=1")
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK")
                    raise
            row = self.db.execute(
                "SELECT project,owner_key,state FROM eai_live_control "
                "WHERE id=1").fetchone()
            if (row is None or row[:2] != (project_id, owner_key_sha256)
                    or row[2] not in ("READY", "HOLD")
                    or self.db.execute("PRAGMA integrity_check").fetchone()[0]
                    != "ok"):
                raise PermissionError("untrusted live ledger project or state")
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def reserve(self, *, nonce: str, now: int, tokens: int) -> str:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            state = self.db.execute(
                "SELECT state FROM eai_live_control WHERE id=1").fetchone()
            latest = self.db.execute(
                "SELECT MAX(utc) FROM eai_live_reservations").fetchone()[0]
            if state != ("READY",):
                reason = "HOLD_PERSISTENT_LIVE_BREAKER"
            elif latest is not None and now < latest:
                reason = "HOLD_NONMONOTONIC_LIVE_TIME"
            elif self.db.execute(
                "SELECT 1 FROM eai_live_reservations WHERE nonce=?",
                (nonce,)).fetchone():
                reason = "HOLD_LIVE_REPLAY"
            else:
                day = self.db.execute(
                    "SELECT COUNT(*) FROM eai_live_reservations "
                    "WHERE utc>? AND utc<=?", (now - 86400, now)).fetchone()[0]
                rpm, tpm = self.db.execute(
                    "SELECT COUNT(*),COALESCE(SUM(tokens),0) "
                    "FROM eai_live_reservations WHERE utc>? AND utc<=?",
                    (now - 60, now)).fetchone()
                if day >= _LIVE_MAX_RPD or rpm >= _LIVE_MAX_RPM:
                    reason = "HOLD_LIVE_LOCAL_QUOTA"
                elif tpm + tokens > _LIVE_MAX_TPM:
                    reason = "HOLD_LIVE_TOKEN_QUOTA"
                else:
                    self.db.execute(
                        "INSERT INTO eai_live_reservations "
                        "VALUES(?,?,?,'RESERVED_UNKNOWN_DELIVERY')",
                        (nonce, now, tokens))
                    reason = "RESERVED"
            self.db.execute("COMMIT")
            return reason
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def settle(self, nonce: str, *, success: bool) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if success:
                self.db.execute(
                    "UPDATE eai_live_reservations SET status='UNTRUSTED_REPLY' "
                    "WHERE nonce=?", (nonce,))
            else:
                self.db.execute("UPDATE eai_live_control SET state='HOLD' "
                                "WHERE id=1")
                self.db.execute(
                    "UPDATE eai_live_reservations SET status='FAILED_HOLD' "
                    "WHERE nonce=?", (nonce,))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise


def dispatch_live_hydrogen(
    packet: ResearchPacket, baseline: object, *, coordinator: ResearchCoordinator,
    api_key: str, owner_permit: SignedLiveSendPermit | None,
    live_ledger_path, allow_ledger_create: bool = False,
) -> LiveHydrogenResult:
    """Real HTTPS code path; default OFF, no implicit credential or entitlement.

    P1 builds this path but does NOT execute it against Google. Before a real
    call the owner must separately approve remote transfer, verify their actual
    model/project free tier, review the exact bytes, pin a signing root and
    create an isolated project ledger. An owner signature cannot guarantee
    provider billing. No automatic paid fallbacks, retries, redirects or tools.
    """
    checked = _packet(packet)
    if type(coordinator) is not ResearchCoordinator:
        raise ValueError("typed coordinator required")
    sha = checked.request_sha256()
    if coordinator.policy.mode is ResearchMode.OFF:
        return LiveHydrogenResult(baseline, "OFF", sha)
    if not coordinator.policy.allows_remote_proposal():
        return LiveHydrogenResult(baseline, "HOLD_OWNER_OR_FREE_TIER", sha)
    if type(api_key) is not str or not _KEY.fullmatch(api_key):
        return LiveHydrogenResult(baseline, "HOLD_MISSING_API_CREDENTIAL", sha)
    draft = build_hydrogen_request_preview(checked)
    from time import time
    now = int(time())
    try:
        if owner_permit is None:
            raise PermissionError("separately signed per-send approval required")
        project, nonce, owner_key = _check_live_owner_permit(
            owner_permit, checked, draft, api_key, now)
    except (PermissionError, ValueError, TypeError):
        return LiveHydrogenResult(baseline, "HOLD_SIGNED_OWNER_APPROVAL", sha)
    # The existing mock quota is NEVER used to authorize real sends.
    budget = max(1, (len(draft.payload) + 3) // 4)
    if budget > _LIVE_MAX_INPUT_TOKENS:
        return LiveHydrogenResult(baseline, "HOLD_LIVE_PAYLOAD_TOKEN_CAP", sha)
    try:
        ledger = _LiveSendLedger(
            live_ledger_path, project_id=project, owner_key_sha256=owner_key,
            allow_create=allow_ledger_create)
    except (OSError, ValueError, PermissionError, TypeError):
        return LiveHydrogenResult(baseline, "HOLD_LIVE_LEDGER_UNAVAILABLE", sha)
    try:
        gate = ledger.reserve(nonce=nonce, now=now,
                              tokens=budget + _LIVE_MAX_OUTPUT_TOKENS)
        if gate != "RESERVED":
            return LiveHydrogenResult(baseline, gate, sha)
        # HTTPS endpoint, method and model are fixed; redirects and proxies
        # are never followed. http.client validates certificates by default.
        import http.client
        import ssl
        conn = None
        ok = False
        try:
            conn = http.client.HTTPSConnection(
                _LIVE_HOST, timeout=8, context=ssl.create_default_context())
            conn.request("POST", _LIVE_PATH, body=draft.payload, headers={
                "x-goog-api-key": api_key, "Content-Type": "application/json",
                "Accept": "application/json",
            })
            resp = conn.getresponse()
            if resp.status != 200:
                return LiveHydrogenResult(
                    baseline, "OFF_AFTER_PROVIDER_HTTP_ERROR", sha,
                    reason="NO_PAID_RETRY_OR_FALLBACK", requests_attempted=1)
            body = resp.read(_MAX_RESPONSE_BYTES + 1)
            if len(body) > _MAX_RESPONSE_BYTES:
                return LiveHydrogenResult(
                    baseline, "OFF_AFTER_OVERSIZE_RESPONSE", sha,
                    requests_attempted=1)
            review = review_hydrogen_response(
                checked, baseline, body, coordinator=coordinator)
            if review.disposition != "LOCAL_UNTRUSTED_IDEAS_REVIEW_ONLY":
                return LiveHydrogenResult(
                    baseline, "OFF_AFTER_INVALID_PROVIDER_CONTENT", sha,
                    requests_attempted=1)
            if coordinator.policy.mode is ResearchMode.OFF:
                return LiveHydrogenResult(
                    baseline, "OFF_LATE_PROVIDER_RESPONSE_IGNORED", sha,
                    requests_attempted=1)
            ok = True
            return LiveHydrogenResult(
                baseline, "UNTRUSTED_HYDROGEN_IDEAS_QUARANTINED",
                sha, review.ideas, "OWNER_ATTESTED_FREE_NOT_PROVIDER_VERIFIED",
                requests_attempted=1)
        except (OSError, ValueError, TimeoutError):
            return LiveHydrogenResult(
                baseline, "OFF_AFTER_PROVIDER_TRANSPORT_FAILURE", sha,
                requests_attempted=1)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except OSError:
                    pass  # Never mask a failed send or skip the breaker.
            # A crash before settlement retains the consumed nonce. A
            # settlement error raises closed; failure must still disable ON.
            try:
                ledger.settle(nonce, success=ok)
            finally:
                if not ok:
                    coordinator.disable()
    finally:
        ledger.close()
