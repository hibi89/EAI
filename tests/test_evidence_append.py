"""Reopening a local evidence ledger requires explicit append authorization."""
import tempfile
import unittest
from pathlib import Path
from eai.evidence_ledger import EvidenceLedger

class SyntheticStore:
    def __init__(self, root):
        self.root = root
    def get(self, digest):
        if digest not in ("a"*64,"b"*64):
            raise KeyError(digest)
        return "synthetic"

class AppendModeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = SyntheticStore(Path(temp.name))

    def test_reopen_append_and_read_only_default(self):
        with EvidenceLedger(self.store, create=True) as ledger:
            first = ledger.append(claim_id="data.x",source_sha256="a"*64,
                                  polarity="SUPPORT",observed_at=1,expires_at=200,now=50)
        with EvidenceLedger(self.store, append_existing=True) as ledger:
            second = ledger.append(claim_id="data.x",source_sha256="b"*64,
                                   polarity="REFUTE",observed_at=2,expires_at=200,now=50)
            self.assertNotEqual(first,second)
            self.assertEqual(ledger.assess("data.x",now=100).state,
                             "CONTRADICTED_UNVERIFIED")
        with EvidenceLedger(self.store) as ledger:
            self.assertEqual(ledger.assess("data.x",now=100).state,
                             "CONTRADICTED_UNVERIFIED")
            with self.assertRaises(PermissionError):
                ledger.append(claim_id="data.x",source_sha256="a"*64,
                              polarity="SUPPORT",observed_at=1,expires_at=200,now=50)

    def test_fail_closed_write_modes(self):
        with self.assertRaises(ValueError):
            EvidenceLedger(self.store,create=True,append_existing=True)
        with self.assertRaises(FileNotFoundError):
            EvidenceLedger(self.store,append_existing=True)


if __name__=="__main__":
    unittest.main()
