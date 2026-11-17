"""Synthetic architect runtime must never treat claims as proof or tool authority."""
import json
from pathlib import Path
import tempfile
import time
import unittest

from eai.axnode_store import AXNodeStore
from eai.architect_runtime import preview_architecture
from eai.evidence_ledger import EvidenceLedger


class EvidenceArchitectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "library"
        self.spec = Path(tmp.name) / "problem.json"
        self.spec.write_text(json.dumps({
            "version":1, "id":"synthetic.evidence",
            "goal":"PRIVATE synthetic owner note never enters claims",
            "domain":"data", "state_refs":[], "assumptions":[],
            "hard_constraints":[], "objectives":["accuracy"],
            "oracle":"fixture.check", "permissions":["local.read"],
            "budget":{"max_steps":5, "max_seconds":80}, "risk":"LOW"
        }), encoding="utf-8")
        with AXNodeStore(self.root) as store:
            self.anchors = []
            for ident in ("data.first", "data.second"):
                self.anchors.append(store.import_node(json.dumps({
                    "schema":"eai.axnode.v1", "id":ident, "version":1,
                    "kind":"strategy", "status":"CANDIDATE",
                    "signature":{"inputs":{"source":"csv_ref"},
                                 "output":"difference_receipt"},
                    "pre":["authorized_read_only"],"post":["verify_later"],
                    "steps":[{"skill":"csv.reconcile.v1"}],
                    "capabilities":["local.read"], "parent_hashes":[],
                    "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
                    "provenance":{"author":"eai_synthetic","source":"synthetic_fixture"},
                    "budget":{"max_steps":2,"max_seconds":20}
                })))

    def _append(self, data):
        now = int(time.time())
        with AXNodeStore(self.root) as store:
            with EvidenceLedger(store, create=not (self.root / "evidence_ledger.sqlite").exists()) as ledger:
                # Open existing writer is disallowed by design; observations for
                # the test must be appended in the same exclusive creation block.
                for polarity, identifier, sha, expired in data:
                    ledger.append(claim_id=identifier,source_sha256=sha,
                                  polarity=polarity, observed_at=now-30,
                                  expires_at=now-1 if expired else now+100,
                                  now=now)

    def test_no_ledger_is_unknown_and_no_sidecar_created(self):
        response=preview_architecture(self.spec,self.root)
        self.assertEqual(response["status"],"CANDIDATES_UNVERIFIED")
        self.assertEqual(response["evidence_claims"],[])
        self.assertFalse((self.root / "evidence_ledger.sqlite").exists())

    def test_unverified_refutation_forces_advisory_hold(self):
        self._append([("REFUTE","data.first",self.anchors[0],False)])
        response=preview_architecture(self.spec,self.root)
        self.assertEqual(response["status"],"BLOCKED_EVIDENCE_DISPUTE")
        self.assertTrue(response["evidence_review_required"])
        self.assertEqual(response["advisory_plans"],[])
        self.assertEqual(response["truth_status"],"UNVERIFIED")
        self.assertNotIn("PRIVATE synthetic owner note",json.dumps(response))

    def test_supported_claim_does_not_become_verified(self):
        self._append([("SUPPORT","data.first",self.anchors[0],False)])
        response=preview_architecture(self.spec,self.root)
        claim=next(x for x in response["evidence_claims"] if x["id"]=="data.first")
        self.assertEqual(claim["state"],"SUPPORTED_UNVERIFIED")
        self.assertEqual(claim["trust"],"NO_INDEPENDENT_VERIFIER")
        self.assertEqual(response["truth_status"],"UNVERIFIED")

    def test_stale_observation_is_unknown_not_verification(self):
        self._append([("REFUTE","data.first",self.anchors[0],True)])
        response=preview_architecture(self.spec,self.root)
        claim=next(x for x in response["evidence_claims"] if x["id"]=="data.first")
        self.assertEqual(claim["state"],"STALE_UNVERIFIED")
        self.assertFalse(response["evidence_review_required"])

    def test_corrupted_evidence_cannot_be_used_as_fact(self):
        self._append([("SUPPORT","data.first",self.anchors[0],False)])
        path=self.root / "evidence_ledger.sqlite"
        with __import__("sqlite3").connect(path) as db:
            db.execute("UPDATE observations SET polarity='REFUTE'")
        with self.assertRaisesRegex(ValueError,"tampered"):
            preview_architecture(self.spec,self.root)


if __name__=="__main__":
    unittest.main()
