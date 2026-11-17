"""Fake HTTP diagnostics and preservation of prior live-ledger rows."""
from __future__ import annotations

import http.client
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eai.contracts import canonical_bytes
from eai.hydrogen_adapter import (
    _LiveSendLedger, _ledger_failure_status, _provider_http_failure_reason,
)


class FakeErrorResponse:
    def __init__(self, status: int, body: bytes = b""):
        self.status = status
        self.body = body

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class IncompleteErrorResponse(FakeErrorResponse):
    def read(self, _limit: int) -> bytes:
        raise http.client.IncompleteRead(b"{\"error\":", 20)


class HydrogenLiveHttpDiagnosticsTests(unittest.TestCase):
    def test_google_http_code_and_allowlisted_status_are_retained(self):
        body = canonical_bytes({"error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "message": "private diagnostic text is intentionally omitted",
        }})
        reason = _provider_http_failure_reason(FakeErrorResponse(429, body))
        self.assertEqual(
            reason, "HTTP_429_RESOURCE_EXHAUSTED_NO_PAID_RETRY_OR_FALLBACK")
        self.assertEqual(_ledger_failure_status(reason),
                         "FAILED_HOLD_" + reason)

    def test_incomplete_http_error_body_keeps_numeric_status(self):
        reason = _provider_http_failure_reason(IncompleteErrorResponse(400))
        self.assertEqual(reason, "HTTP_400_UNCLASSIFIED_NO_PAID_RETRY_OR_FALLBACK")

    def test_unknown_google_status_and_untrusted_reason_are_not_persisted(self):
        body = canonical_bytes({"error": {
            "status": "SENSITIVE_INTERNAL_TEXT",
            "message": "key-or-prompt-content-must-not-appear",
        }})
        reason = _provider_http_failure_reason(FakeErrorResponse(403, body))
        self.assertEqual(reason, "HTTP_403_UNCLASSIFIED_NO_PAID_RETRY_OR_FALLBACK")
        self.assertNotIn("SENSITIVE", reason)
        self.assertEqual(_ledger_failure_status("anything private"), "FAILED_HOLD")

    def test_diagnostic_updates_only_the_new_reservation_without_schema_change(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "live.sqlite"
            ledger = _LiveSendLedger(
                    path, project_id="eai-test-project",
                    owner_key_sha256="a" * 64, allow_create=True)
            try:
                self.assertEqual(ledger.reserve(
                    nonce="A" * 24, now=1000, tokens=40), "RESERVED")
                self.assertEqual(ledger.reserve(
                    nonce="B" * 24, now=1001, tokens=40), "RESERVED")
                before_version = ledger.db.execute(
                    "PRAGMA user_version").fetchone()[0]
                reason = "HTTP_429_RESOURCE_EXHAUSTED_NO_PAID_RETRY_OR_FALLBACK"
                ledger.settle("B" * 24, success=False, failure_reason=reason)
                rows = dict(ledger.db.execute(
                    "SELECT nonce,status FROM eai_live_reservations"))
                self.assertEqual(rows["A" * 24], "RESERVED_UNKNOWN_DELIVERY")
                self.assertEqual(rows["B" * 24], "FAILED_HOLD_" + reason)
                self.assertEqual(ledger.db.execute(
                    "SELECT state FROM eai_live_control WHERE id=1").fetchone(),
                    ("HOLD",))
                self.assertEqual(ledger.db.execute(
                    "PRAGMA user_version").fetchone()[0], before_version)
            finally:
                ledger.close()


if __name__ == "__main__":
    unittest.main()
