"""Synthetic-only sidecar provenance, freshness, no-overwrite and corruption guards."""
from pathlib import Path
import tempfile
import unittest
from typing import Any, TypedDict, cast

from eai.evidence_ledger import EvidenceLedger


class AppendKw(TypedDict):
    claim_id: str
    source_sha256: str
    polarity: str
    observed_at: int
    expires_at: int
    now: int


class SyntheticStore:
    def __init__(self, root):
        self.root = root
        self.nodes = {"a"*64: b"content-A", "b"*64: b"content-B"}

    def get(self, digest):
        if digest not in self.nodes:
            raise KeyError("unknown evidence anchor")
        return self.nodes[digest]


class EvidenceLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SyntheticStore(self.root)
        self.path = self.root / "evidence_ledger.sqlite"

    def test_append_and_reopen_read_only_is_not_verified(self):
        with EvidenceLedger(self.store, create=True) as ledger:
            digest = ledger.append(claim_id="data.first", source_sha256="a"*64,
                                   polarity="SUPPORT", observed_at=100,
                                   expires_at=200, now=150)
        with EvidenceLedger(self.store) as reader:
            result = reader.assess("data.first", now=150)
            self.assertEqual(result.state, "SUPPORTED_UNVERIFIED")
            self.assertEqual(result.supporting_hashes, (digest,))
            self.assertEqual(result.trust, "NO_INDEPENDENT_VERIFIER")
            with self.assertRaises(PermissionError):
                reader.append(claim_id="data.first", source_sha256="a"*64,
                              polarity="REFUTE", observed_at=100,
                              expires_at=200, now=150)

    def test_conflict_blocks_trust(self):
        with EvidenceLedger(self.store, create=True) as writer:
            writer.append(claim_id="data.first", source_sha256="a"*64,
                          polarity="SUPPORT", observed_at=100,
                          expires_at=200, now=150)
            writer.append(claim_id="data.first", source_sha256="b"*64,
                          polarity="REFUTE", observed_at=101,
                          expires_at=200, now=150)
            self.assertEqual(writer.assess("data.first", now=150).state,
                             "CONTRADICTED_UNVERIFIED")

    def test_expiry_is_stale_not_automatically_deleted(self):
        with EvidenceLedger(self.store, create=True) as ledger:
            digest = ledger.append(claim_id="data.first", source_sha256="a"*64,
                                   polarity="SUPPORT", observed_at=100,
                                   expires_at=110, now=105)
            result = ledger.assess("data.first", now=110)
            self.assertEqual(result.state, "STALE_UNVERIFIED")
            self.assertEqual(result.stale_hashes,(digest,))
            self.assertEqual(ledger.db.execute("SELECT count(*) FROM observations").fetchone()[0],1)

    def test_unknown_never_claims_false_verified(self):
        with EvidenceLedger(self.store, create=True) as ledger:
            result = ledger.assess("data.never", now=100)
            self.assertEqual(result.state,"UNKNOWN")
            self.assertEqual(result.supporting_hashes, ())

    def test_repeat_is_idempotent_and_no_overwrite(self):
        with EvidenceLedger(self.store, create=True) as ledger:
            kw: AppendKw = dict(claim_id="data.first",source_sha256="a"*64,
                    polarity="SUPPORT",observed_at=50,expires_at=90,now=60)
            self.assertEqual(ledger.append(**kw),ledger.append(**kw))
            self.assertEqual(ledger.db.execute("SELECT count(*) FROM observations").fetchone()[0],1)
        before=self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            EvidenceLedger(self.store, create=True)
        self.assertEqual(self.path.read_bytes(),before)

    def test_reject_private_prompts_weak_timestamps_and_unpinned_anchors(self):
        with EvidenceLedger(self.store, create=True) as ledger:
            base: AppendKw = dict(claim_id="data.first",source_sha256="a"*64,
                      polarity="SUPPORT",observed_at=100,expires_at=150,now=100)
            for key,value in [("claim_id","private raw prompt"),
                              ("source_sha256","x"*64),
                              ("polarity","VERIFIED"),
                              ("observed_at",101),
                              ("expires_at",100)]:
                with self.subTest(key=key), self.assertRaises((ValueError,KeyError)):
                    ledger.append(**cast(Any, dict(base,**{key:value})))

    def test_detects_db_metadata_forgery_without_trusting_payload(self):
        with EvidenceLedger(self.store, create=True) as ledger:
            digest=ledger.append(claim_id="data.first",source_sha256="a"*64,
                                 polarity="SUPPORT",observed_at=100,
                                 expires_at=150,now=100)
            ledger.db.execute("UPDATE observations SET polarity='REFUTE' WHERE sha256=?",(digest,))
            ledger.db.commit()
            with self.assertRaisesRegex(ValueError,"metadata tampered"):
                ledger.assess("data.first",now=110)

    def test_reject_symlink_and_modified_anchor(self):
        with EvidenceLedger(self.store, create=True) as ledger:
            ledger.append(claim_id="data.first",source_sha256="a"*64,
                          polarity="SUPPORT",observed_at=100,expires_at=150,now=100)
        self.store.nodes.clear()
        with EvidenceLedger(self.store) as ledger:
            with self.assertRaises(KeyError):
                ledger.assess("data.first",now=110)
        other=self.root / "badroot"
        other.mkdir()
        try:
            (other / 'evidence_ledger.sqlite').symlink_to(self.path)
        except (OSError,NotImplementedError):
            return
        with self.assertRaises(ValueError):
            EvidenceLedger(SyntheticStore(other))


if __name__ == '__main__':
    unittest.main()
