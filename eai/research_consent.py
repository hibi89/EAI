"""EAI-SWU-035 append-only LOCAL research preview review, not remote consent.

All real Hydrogen sends, subscriptions, tiers and API access stay HOLD.
No packet abstract, credential or personal information is written to this
ledger; a caller-supplied boolean never constitutes human identity proof.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path

from .contracts import canonical_bytes, strict_json
from .hydrogen_packet import ResearchPacket


@dataclass(frozen=True)
class ResearchReviewReceipt:
    request_sha256: str
    preview_sha256: str
    disposition: str
    review_record_sha256: str | None
    remote_authorized: bool = False
    can_send: bool = False
    paid_access_enabled: bool = False


def record_local_packet_review(
    packet: ResearchPacket, review_directory: str | Path, *,
    reviewed_preview_sha256: str,
    reviewed: bool = False,
) -> ResearchReviewReceipt:
    """Bind one exact synthetic/public packet to an immutable local review row.

    The directory must already be owner-selected and owned separately; no
    directory creation or overwrite. This API cannot be used by a live sender.
    """
    if type(packet) is not ResearchPacket:
        raise ValueError("typed synthetic research packet required")
    checked = ResearchPacket.from_json(packet.to_json_bytes())
    request_sha = checked.request_sha256()
    preview_sha = hashlib.sha256(
        checked.review_exact_outbound_text().encode("utf-8")).hexdigest()
    if type(reviewed) is not bool or type(reviewed_preview_sha256) is not str:
        raise ValueError("explicit local review fields required")
    if not reviewed or reviewed_preview_sha256 != preview_sha:
        return ResearchReviewReceipt(
            request_sha, preview_sha, "HOLD_EXACT_PREVIEW_NOT_REVIEWED", None)
    directory = Path(review_directory).expanduser()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("explicit existing local review directory required")
    record = {
        "schema": "eai.local.research.review.v1",
        "request_sha256": request_sha,
        "preview_sha256": preview_sha,
        "nonce": checked.nonce,
        "visibility": "PUBLIC_SYNTHETIC_ONLY",
        "disposition": "LOCAL_REVIEW_ONLY_NO_REMOTE_APPROVAL",
    }
    data = canonical_bytes(record)
    digest = hashlib.sha256(data).hexdigest()
    target = directory / (request_sha + ".review.json")
    if target.is_symlink():
        raise ValueError("review record symlink is forbidden")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        if target.is_symlink() or not target.is_file():
            raise ValueError("existing review record is unsafe")
        existing = target.read_bytes()
        if len(existing) > 1024 or existing != data or (
                strict_json(existing, max_bytes=1024) != record):
            raise ValueError("review record conflict or tampering")
        return ResearchReviewReceipt(
            request_sha, preview_sha, "HOLD_DUPLICATE_PACKET_REVIEW", digest)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # Preserve partial evidence for owner audit, never auto-delete data.
        raise
    return ResearchReviewReceipt(
        request_sha, preview_sha,
        "LOCAL_REVIEW_RECORDED_REMOTE_STILL_HOLD", digest)
