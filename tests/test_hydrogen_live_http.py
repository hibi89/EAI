"""Fake HTTP diagnostics and preservation of prior live-ledger rows."""
from __future__ import annotations

from contextlib import closing
import http.client
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from typing import cast
from unittest.mock import patch

from eai.contracts import canonical_bytes
from eai.hydrogen_packet import ResearchPacket
from eai.hydrogen_adapter import (
    _LiveSendLedger, _ledger_failure_status, _live_request_id,
    _provider_http_failure_reason, _read_external_owner_trust_root,
    build_hydrogen_request_preview,
    dispatch_live_hydrogen, SignedLiveSendPermit,
)
from eai.research_policy import ResearchMode, ResearchPolicy
from eai.research_providers import ResearchCoordinator


class FakeErrorResponse:
    def __init__(self, status: int, body: bytes = b""):
        self.status = status
        self.body = body

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class IncompleteErrorResponse(FakeErrorResponse):
    def read(self, _limit: int) -> bytes:
        raise http.client.IncompleteRead(b"{\"error\":", 20)


class FakeConnection:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []
        self.closed = False

    def request(self, method, path, *, body, headers):
        self.requests.append((method, path, body, dict(headers)))

    def getresponse(self):
        if self.error is not None:
            raise self.error
        return self.response

    def close(self):
        self.closed = True


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

    def test_major_google_http_failure_classes_remain_bounded(self):
        for code, status in (
            (400, "INVALID_ARGUMENT"),
            (403, "PERMISSION_DENIED"),
            (404, "NOT_FOUND"),
            (429, "RESOURCE_EXHAUSTED"),
            (503, "UNAVAILABLE"),
        ):
            with self.subTest(code=code):
                body = canonical_bytes({"error": {
                    "code": code, "status": status,
                    "message": "untrusted message not retained",
                }})
                reason = _provider_http_failure_reason(
                    FakeErrorResponse(code, body))
                self.assertEqual(
                    reason,
                    f"HTTP_{code}_{status}_NO_PAID_RETRY_OR_FALLBACK")
                self.assertNotIn("untrusted message", reason)

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
        request_id = _live_request_id("eai-test-project", "N" * 24, "a" * 64)
        self.assertEqual(
            _ledger_failure_status("anything private", request_id),
            "FAILED_HOLD_RID_" + request_id[5:])

    def test_local_request_id_is_stable_opaque_and_bound_to_signed_nonce(self):
        project, nonce = "eai-test-project", "N" * 24
        packet_sha = "b" * 64
        first = _live_request_id(project, nonce, packet_sha)
        self.assertRegex(first, r"^eaih_[0-9a-f]{24}$")
        self.assertEqual(first, _live_request_id(project, nonce, packet_sha))
        self.assertNotEqual(first, _live_request_id(project, "M" * 24, packet_sha))
        self.assertNotEqual(first, _live_request_id(project, nonce, "c" * 64))
        self.assertNotIn(nonce, first)


    def test_live_settlement_requires_unmodified_pending_row(self):
        """A forged success cannot finalize a never-reserved or erased nonce."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "live.sqlite"
            ledger = _LiveSendLedger(
                path, project_id="eai-test-project",
                owner_key_sha256="a" * 64, allow_create=True)
            try:
                nonce = "N" * 24
                with self.assertRaises(PermissionError):
                    ledger.settle(nonce, success=True)
                self.assertEqual(
                    ledger.db.execute("SELECT state FROM eai_live_control "
                                      "WHERE id=1").fetchone(), ("HOLD",))
                self.assertEqual(ledger.db.execute(
                    "SELECT COUNT(*) FROM eai_live_reservations").fetchone(),
                    (0,))
            finally:
                ledger.close()

    def test_live_settlement_deleted_row_or_replayed_result_stays_hold(self):
        for mutate in ("DELETE", "SETTLED", "HOLD_CONTROL"):
            with self.subTest(mutate=mutate), TemporaryDirectory() as directory:
                ledger = _LiveSendLedger(
                    Path(directory) / "live.sqlite",
                    project_id="eai-test-project",
                    owner_key_sha256="a" * 64, allow_create=True)
                try:
                    nonce = "N" * 24
                    self.assertEqual(ledger.reserve(
                        nonce=nonce, now=1700000000, tokens=120), "RESERVED")
                    if mutate == "DELETE":
                        ledger.db.execute(
                            "DELETE FROM eai_live_reservations WHERE nonce=?",
                            (nonce,))
                    elif mutate == "SETTLED":
                        ledger.settle(nonce, success=True)
                    else:
                        ledger.db.execute(
                            "UPDATE eai_live_control SET state='HOLD' "
                            "WHERE id=1")
                    with self.assertRaises(PermissionError):
                        ledger.settle(nonce, success=True)
                    self.assertEqual(
                        ledger.db.execute(
                            "SELECT state FROM eai_live_control WHERE id=1")
                        .fetchone(), ("HOLD",))
                    if mutate == "SETTLED":
                        self.assertEqual(
                            ledger.db.execute(
                                "SELECT status FROM eai_live_reservations "
                                "WHERE nonce=?", (nonce,)).fetchone(),
                            ("UNTRUSTED_REPLY",))
                    elif mutate == "DELETE":
                        self.assertEqual(ledger.db.execute(
                            "SELECT COUNT(*) FROM eai_live_reservations")
                            .fetchone(), (0,))
                    else:
                        self.assertEqual(ledger.db.execute(
                            "SELECT status FROM eai_live_reservations "
                            "WHERE nonce=?", (nonce,)).fetchone(),
                            ("RESERVED_UNKNOWN_DELIVERY",))
                finally:
                    ledger.close()

    def test_live_failure_settlement_requires_reservation_and_holds(self):
        with TemporaryDirectory() as directory:
            ledger = _LiveSendLedger(
                Path(directory) / "live.sqlite",
                project_id="eai-test-project",
                owner_key_sha256="a" * 64, allow_create=True)
            try:
                nonce = "N" * 24
                self.assertEqual(ledger.reserve(
                    nonce=nonce, now=1700000000, tokens=100), "RESERVED")
                ledger.settle(nonce, success=False,
                              failure_reason="TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY")
                self.assertEqual(ledger.db.execute(
                    "SELECT state FROM eai_live_control WHERE id=1").fetchone(),
                    ("HOLD",))
                self.assertEqual(ledger.db.execute(
                    "SELECT status FROM eai_live_reservations WHERE nonce=?",
                    (nonce,)).fetchone(),
                    ("FAILED_HOLD_TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY",))
                with self.assertRaises(PermissionError):
                    ledger.settle(nonce, success=True)
                self.assertEqual(ledger.reserve(
                    nonce="M" * 24, now=1700000001, tokens=100),
                    "HOLD_PERSISTENT_LIVE_BREAKER")
            finally:
                ledger.close()

    def test_existing_live_ledger_hardlink_is_rejected_without_mutating_owner_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "owner_original.bin"
            original.write_bytes(b"OWNER_ORIGINAL_UNTOUCHED")
            linked = root / "live.sqlite"
            try:
                os.link(original, linked)
            except (OSError, NotImplementedError):
                self.skipTest("hardlinks unavailable on this filesystem")
            before = original.read_bytes()
            with self.assertRaises((ValueError, PermissionError)):
                _LiveSendLedger(linked, project_id="eai-test-project",
                                owner_key_sha256="a" * 64, allow_create=True)
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual(linked.read_bytes(), before)

    def test_live_sqlite_sidecar_hardlinks_fail_before_ledger_creation(self):
        for suffix in ("-wal", "-shm", "-journal"):
            with self.subTest(suffix=suffix), TemporaryDirectory() as directory:
                root = Path(directory)
                original = root / "owner_original.bin"
                original.write_bytes(b"OWNER_ORIGINAL_UNTOUCHED")
                ledger_path = root / "live.sqlite"
                try:
                    os.link(original, Path(str(ledger_path) + suffix))
                except (OSError, NotImplementedError):
                    self.skipTest("hardlinks unavailable on this filesystem")
                with self.assertRaises((ValueError, PermissionError)):
                    _LiveSendLedger(ledger_path, project_id="eai-test-project",
                                    owner_key_sha256="a" * 64, allow_create=True)
                self.assertEqual(original.read_bytes(), b"OWNER_ORIGINAL_UNTOUCHED")
                self.assertFalse(ledger_path.exists())

    def test_live_ledger_rejects_forged_triggers_and_views_on_reopen(self):
        for object_ddl in (
            "CREATE VIEW forged_review AS SELECT state FROM eai_live_control",
            "CREATE TRIGGER forged_mutation AFTER UPDATE ON eai_live_control "
            "BEGIN UPDATE eai_live_reservations SET status='CLAIM_VERIFIED'; END",
        ):
            with self.subTest(ddl=object_ddl), TemporaryDirectory() as directory:
                path = Path(directory) / "live.sqlite"
                ledger = _LiveSendLedger(
                    path, project_id="eai-test-project",
                    owner_key_sha256="a" * 64, allow_create=True)
                ledger.close()
                with closing(sqlite3.connect(path)) as db:
                    db.execute(object_ddl)
                    db.commit()
                with self.assertRaisesRegex(PermissionError,
                                             "unexpected live ledger schema objects"):
                    _LiveSendLedger(
                        path, project_id="eai-test-project",
                        owner_key_sha256="a" * 64)
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(
                        db.execute("SELECT state FROM eai_live_control WHERE id=1")
                        .fetchone(), ("READY",))
                    self.assertEqual(db.execute(
                        "SELECT COUNT(*) FROM eai_live_reservations").fetchone()[0], 0)


    def test_live_ledger_refuses_foreign_same_column_weak_schema(self):
        """Matching names do not authorize weaker source-file constraints."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "live.sqlite"
            with closing(sqlite3.connect(path)) as db:
                db.executescript(
                    "CREATE TABLE eai_live_control("
                    "id INTEGER PRIMARY KEY, project TEXT NOT NULL, "
                    "owner_key TEXT NOT NULL, state TEXT NOT NULL);"
                    "CREATE TABLE eai_live_reservations("
                    "nonce TEXT PRIMARY KEY, utc INTEGER NOT NULL, "
                    "tokens INTEGER NOT NULL, status TEXT NOT NULL);")
                db.execute("INSERT INTO eai_live_control VALUES(1,?,?,?)",
                           ("eai-test-project", "a" * 64, "READY"))
                db.execute("PRAGMA user_version=1")
                db.commit()
            before = path.read_bytes()
            with self.assertRaisesRegex(PermissionError,
                                        "unexpected live ledger schema objects"):
                _LiveSendLedger(path, project_id="eai-test-project",
                                owner_key_sha256="a" * 64)
            self.assertEqual(path.read_bytes(), before)

    def test_live_ledger_refuses_extra_index_before_external_reservation(self):
        """An unapproved index must not govern a future live quota write."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "live.sqlite"
            ledger = _LiveSendLedger(
                path, project_id="eai-test-project",
                owner_key_sha256="a" * 64, allow_create=True)
            ledger.close()
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE UNIQUE INDEX forged_status "
                           "ON eai_live_reservations(status)")
                db.commit()
            before = path.read_bytes()
            with self.assertRaisesRegex(PermissionError,
                                        "unexpected live ledger schema objects"):
                _LiveSendLedger(path, project_id="eai-test-project",
                                owner_key_sha256="a" * 64)
            self.assertEqual(path.read_bytes(), before)

    @staticmethod
    def owner_root_bytes() -> bytes:
    @staticmethod
    def owner_root_bytes() -> bytes:
        return canonical_bytes({
            "schema": "eai.hydrogen.owner.root.v1",
            "project_id": "eai-test-project",
            "owner_key_sha256": "a" * 64,
        })

    def test_owner_trust_root_requires_absolute_ordinary_single_link(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            trust = root / "trusted-root.json"
            trust.write_bytes(self.owner_root_bytes())
            self.assertEqual(
                _read_external_owner_trust_root(trust),
                ("eai-test-project", "a" * 64))
            with self.assertRaises(PermissionError):
                _read_external_owner_trust_root(Path("trusted-root.json"))
            with self.assertRaises(PermissionError):
                _read_external_owner_trust_root(root / "missing-root.json")
            aliased = root / "linked-root.json"
            try:
                os.link(trust, aliased)
            except (OSError, NotImplementedError):
                self.skipTest("hardlinks unavailable on this filesystem")
            with self.assertRaises(PermissionError):
                _read_external_owner_trust_root(aliased)
            with self.assertRaises(PermissionError):
                _read_external_owner_trust_root(trust)
            self.assertEqual(trust.read_bytes(), self.owner_root_bytes())

    def test_owner_trust_root_rejects_symlinked_grandparent_before_send(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            canonical_dir = root / "actual" / "child"
            canonical_dir.mkdir(parents=True)
            trust = canonical_dir / "trusted-root.json"
            trust.write_bytes(self.owner_root_bytes())
            alias = root / "alias"
            try:
                alias.symlink_to(root / "actual", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks unavailable on this host")
            forged_path = alias / "child" / "trusted-root.json"
            with self.assertRaises(PermissionError):
                _read_external_owner_trust_root(forged_path)
            packet = self.packet()
            baseline = object()
            coordinator = ResearchCoordinator(ResearchPolicy(
                mode=ResearchMode.RESEARCH_OPT_IN,
                external_sends_approved=True, free_tier_verified=True))
            ledger = root / "must-not-exist.sqlite"
            with patch("eai.hydrogen_adapter.http.client.HTTPSConnection",
                       side_effect=AssertionError("network must remain closed")):
                result = dispatch_live_hydrogen(
                    packet, baseline, coordinator=coordinator,
                    api_key="A" * 32, owner_permit=None,
                    owner_trust_root_path=forged_path,
                    live_ledger_path=ledger, allow_ledger_create=True)
            self.assertEqual(result.status, "HOLD_OWNER_TRUST_NOT_PROVISIONED")
            self.assertIs(result.baseline, baseline)
            self.assertEqual(result.requests_attempted, 0)
            self.assertFalse(ledger.exists())
            self.assertEqual(trust.read_bytes(), self.owner_root_bytes())

    def test_owner_trust_root_oversized_or_noncanonical_is_untrusted(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "owner-root.json"
            for data in (b"x" * 513,
                         b'{"owner_key_sha256":"' + b"a" * 64
                         + b'","project_id":"eai-test-project","schema":'
                         + b'"eai.hydrogen.owner.root.v1"}\\n',
                         b'{"schema":"eai.hydrogen.owner.root.v1",'
                         + b'"project_id":"eai-test-project",'
                         + b'"owner_key_sha256":"b","owner_key_sha256":"'
                         + b"a" * 64 + b'"}'):
                with self.subTest(data=data[:24]):
                    path.write_bytes(data)
                    with self.assertRaises(PermissionError):
                        _read_external_owner_trust_root(path)

    def test_missing_per_send_consent_holds_before_network_or_ledger_create(self):
        packet = self.packet()
        baseline = object()
        coordinator = ResearchCoordinator(ResearchPolicy(
            mode=ResearchMode.RESEARCH_OPT_IN,
            external_sends_approved=True, free_tier_verified=True))
        with TemporaryDirectory() as directory:
            trust_root = Path(directory) / "owner-root.json"
            trust_root.write_bytes(canonical_bytes({
                "schema": "eai.hydrogen.owner.root.v1",
                "project_id": "eai-test-project",
                "owner_key_sha256": "a" * 64,
            }))
            ledger_path = Path(directory) / "live.sqlite"
            with patch("eai.hydrogen_adapter.http.client.HTTPSConnection",
                       side_effect=AssertionError("network must remain closed")):
                result = dispatch_live_hydrogen(
                    packet, baseline, coordinator=coordinator,
                    api_key="A" * 32, owner_permit=None,
                    owner_trust_root_path=trust_root,
                    live_ledger_path=ledger_path, allow_ledger_create=True)
            self.assertEqual(result.status, "HOLD_SIGNED_OWNER_APPROVAL")
            self.assertIs(result.baseline, baseline)
            self.assertEqual(result.requests_attempted, 0)
            self.assertEqual(result.request_id, "")
            self.assertEqual(coordinator.policy.mode,
                             ResearchMode.RESEARCH_OPT_IN)
            self.assertFalse(ledger_path.exists())

    @staticmethod
    def packet():
        return ResearchPacket.validate({
            "version": 1, "nonce": "syntheticnonce1234",
            "task_family": "synthetic.csv",
            "visibility": "PUBLIC_SYNTHETIC_ONLY",
            "abstract": "Synthetic CSV consistency test",
            "strategy_ids": ["data.csv.key_diff"],
            "objectives": ["detect.counterexample"],
        })

    def run_mock_dispatch(self, directory, connection):
        packet = self.packet()
        baseline = {"offline": "authoritative"}
        coordinator = ResearchCoordinator(ResearchPolicy(
            mode=ResearchMode.RESEARCH_OPT_IN,
            external_sends_approved=True, free_tier_verified=True))
        nonce = "N" * 24
        owner_sha = "a" * 64
        with (patch("eai.hydrogen_adapter._read_external_owner_trust_root",
                    return_value=("eai-test-project", owner_sha)),
              patch("eai.hydrogen_adapter._check_live_owner_permit",
                    return_value=("eai-test-project", nonce, owner_sha)),
              patch("eai.hydrogen_adapter.http.client.HTTPSConnection",
                    return_value=connection)):
            result = dispatch_live_hydrogen(
                packet, baseline, coordinator=coordinator,
                api_key="A" * 32, owner_permit=cast(SignedLiveSendPermit, object()),
                owner_trust_root_path="mocked-only",
                live_ledger_path=Path(directory) / "live.sqlite",
                allow_ledger_create=True)
        return packet, baseline, coordinator, nonce, result

    def test_mocked_generate_content_success_is_quarantined_and_correlated(self):
        packet = self.packet()
        preview = build_hydrogen_request_preview(packet)
        proposal = canonical_bytes({
            "schema": "eai.hydrogen.candidate.idea.v1",
            "request_sha256": packet.request_sha256(),
            "task_family": packet.task_family,
            "hypotheses": [{
                "idea_id": "idea_1", "summary": "synthetic hypothesis",
                "counterexamples": ["case.synthetic"],
                "assumptions": ["fixture.bounded"],
            }],
        }).decode("utf-8")
        body = canonical_bytes({"candidates": [{
            "finishReason": "STOP",
            "content": {"role": "model", "parts": [{"text": proposal}]},
        }]})
        connection = FakeConnection(FakeErrorResponse(200, body))
        with TemporaryDirectory() as directory:
            packet, baseline, coordinator, nonce, result = self.run_mock_dispatch(
                directory, connection)
            self.assertEqual(result.status, "UNTRUSTED_HYDROGEN_IDEAS_QUARANTINED")
            self.assertIs(result.baseline, baseline)
            self.assertEqual(len(result.ideas), 1)
            self.assertEqual(result.request_id,
                             _live_request_id("eai-test-project", nonce,
                                              packet.request_sha256()))
            self.assertEqual(result.requests_attempted, 1)
            self.assertEqual(len(connection.requests), 1)
            method, path, sent_body, headers = connection.requests[0]
            self.assertEqual(method, "POST")
            self.assertEqual(path,
                "/v1beta/models/gemini-4-hydrogen:generateContent")
            self.assertEqual(sent_body, preview.payload)
            self.assertEqual(headers["Content-Type"], "application/json")
            self.assertEqual(headers["x-goog-api-key"], "A" * 32)
            request_json = json.loads(sent_body)
            self.assertIn("contents", request_json)
            self.assertIn("generationConfig", request_json)
            self.assertTrue(connection.closed)
            ledger = _LiveSendLedger(
                Path(directory) / "live.sqlite", project_id="eai-test-project",
                owner_key_sha256="a" * 64)
            try:
                rows = dict(ledger.db.execute(
                    "SELECT nonce,status FROM eai_live_reservations"))
                self.assertEqual(rows[nonce],
                                 "UNTRUSTED_REPLY_RID_" + result.request_id[5:])
            finally:
                ledger.close()
            self.assertEqual(coordinator.policy.mode,
                             ResearchMode.RESEARCH_OPT_IN)

    def test_mocked_http_error_persists_safe_diagnostic_and_never_retries(self):
        body = canonical_bytes({"error": {
            "code": 429, "status": "RESOURCE_EXHAUSTED",
            "message": "do not persist this private provider detail",
        }})
        connection = FakeConnection(FakeErrorResponse(429, body))
        with TemporaryDirectory() as directory:
            _packet, baseline, coordinator, nonce, result = self.run_mock_dispatch(
                directory, connection)
            self.assertEqual(result.status, "OFF_AFTER_PROVIDER_HTTP_ERROR")
            self.assertIs(result.baseline, baseline)
            self.assertEqual(result.reason,
                "HTTP_429_RESOURCE_EXHAUSTED_NO_PAID_RETRY_OR_FALLBACK")
            self.assertRegex(result.request_id, r"^eaih_[0-9a-f]{24}$")
            self.assertEqual(result.requests_attempted, 1)
            self.assertEqual(len(connection.requests), 1)
            self.assertEqual(coordinator.policy.mode, ResearchMode.OFF)
            ledger = _LiveSendLedger(
                Path(directory) / "live.sqlite", project_id="eai-test-project",
                owner_key_sha256="a" * 64)
            try:
                row = ledger.db.execute(
                    "SELECT status FROM eai_live_reservations WHERE nonce=?",
                    (nonce,)).fetchone()
                self.assertEqual(row[0],
                    "FAILED_HOLD_HTTP_429_RESOURCE_EXHAUSTED_"
                    "NO_PAID_RETRY_OR_FALLBACK_RID_" + result.request_id[5:])
                self.assertNotIn("private provider detail", row[0])
                self.assertEqual(ledger.db.execute(
                    "SELECT state FROM eai_live_control WHERE id=1").fetchone(),
                    ("HOLD",))
            finally:
                ledger.close()

    def test_429_pauses_second_send_even_with_stale_approval_and_credential(self):
        body = canonical_bytes({"error": {
            "code": 429, "status": "RESOURCE_EXHAUSTED",
            "message": "never log owner private retry text",
        }})
        conn = FakeConnection(FakeErrorResponse(429, body))
        with TemporaryDirectory() as directory:
            packet, baseline, coordinator, nonce, first = self.run_mock_dispatch(
                directory, conn)
            self.assertEqual(first.status, "OFF_AFTER_PROVIDER_HTTP_ERROR")
            path = Path(directory) / "live.sqlite"
            with patch("eai.hydrogen_adapter.http.client.HTTPSConnection",
                       side_effect=AssertionError("must not retry any network")):
                second = dispatch_live_hydrogen(
                    packet, baseline, coordinator=coordinator,
                    api_key="A" * 32, owner_permit=None,
                    owner_trust_root_path="untrusted",
                    live_ledger_path=path, allow_ledger_create=True)
            self.assertEqual(second.status, "OFF")
            self.assertIs(second.baseline, baseline)
            self.assertEqual(second.requests_attempted, 0)
            self.assertEqual(len(conn.requests), 1)
            ledger = _LiveSendLedger(path, project_id="eai-test-project",
                                     owner_key_sha256="a" * 64)
            try:
                self.assertEqual(ledger.db.execute(
                    "SELECT COUNT(*) FROM eai_live_reservations").fetchone()[0], 1)
                status = ledger.db.execute(
                    "SELECT status FROM eai_live_reservations WHERE nonce=?",
                    (nonce,)).fetchone()[0]
                self.assertIn("HTTP_429_RESOURCE_EXHAUSTED", status)
                self.assertNotIn("private retry text", status)
            finally:
                ledger.close()

    def test_default_off_with_permissive_flags_never_creates_live_ledger(self):
        packet = self.packet()
        baseline = {"trusted_cpu": "synthetic-only"}
        coordinator = ResearchCoordinator(ResearchPolicy(
            mode=ResearchMode.OFF, free_tier_verified=True,
            external_sends_approved=True))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "should_not_exist.sqlite"
            with patch("eai.hydrogen_adapter.http.client.HTTPSConnection",
                       side_effect=AssertionError("network on default OFF")):
                result = dispatch_live_hydrogen(
                    packet, baseline, coordinator=coordinator,
                    api_key="A" * 32, owner_permit=None,
                    owner_trust_root_path=None,
                    live_ledger_path=path, allow_ledger_create=True)
            self.assertEqual(result.status, "OFF")
            self.assertEqual(result.requests_attempted, 0)
            self.assertIs(result.baseline, baseline)
            self.assertFalse(path.exists())
            self.assertEqual(coordinator.policy.mode, ResearchMode.OFF)

    def test_mocked_transport_timeout_is_correlated_and_held_without_retry(self):
        connection = FakeConnection(error=TimeoutError("opaque transport detail"))
        with TemporaryDirectory() as directory:
            _packet, baseline, coordinator, nonce, result = self.run_mock_dispatch(
                directory, connection)
            self.assertEqual(result.status, "OFF_AFTER_PROVIDER_TIMEOUT")
            self.assertEqual(result.reason, "TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY")
            self.assertIs(result.baseline, baseline)
            self.assertEqual(result.requests_attempted, 1)
            self.assertEqual(len(connection.requests), 1)
            self.assertEqual(coordinator.policy.mode, ResearchMode.OFF)
            ledger = _LiveSendLedger(
                Path(directory) / "live.sqlite", project_id="eai-test-project",
                owner_key_sha256="a" * 64)
            try:
                status = ledger.db.execute(
                    "SELECT status FROM eai_live_reservations WHERE nonce=?",
                    (nonce,)).fetchone()[0]
                self.assertEqual(status,
                    "FAILED_HOLD_TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY_RID_"
                    + result.request_id[5:])
                self.assertEqual(ledger.db.execute(
                    "SELECT state FROM eai_live_control WHERE id=1").fetchone(),
                    ("HOLD",))
            finally:
                ledger.close()

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
                request_id = _live_request_id(
                    "eai-test-project", "B" * 24, "c" * 64)
                ledger.settle("B" * 24, success=False, failure_reason=reason,
                              request_id=request_id)
                rows = dict(ledger.db.execute(
                    "SELECT nonce,status FROM eai_live_reservations"))
                self.assertEqual(rows["A" * 24], "RESERVED_UNKNOWN_DELIVERY")
                self.assertEqual(rows["B" * 24],
                    "FAILED_HOLD_" + reason + "_RID_" + request_id[5:])
                self.assertEqual(ledger.db.execute(
                    "SELECT state FROM eai_live_control WHERE id=1").fetchone(),
                    ("HOLD",))
                self.assertEqual(ledger.db.execute(
                    "PRAGMA user_version").fetchone()[0], before_version)
            finally:
                ledger.close()


if __name__ == "__main__":
    unittest.main()
