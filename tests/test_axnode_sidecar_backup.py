"""Synthetic-only isolated WAL snapshot and private sidecar restore safeguards."""
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from eai.axnode_store import AXNodeStore
from eai.axnode_memory import AXNodeMemory
from eai.evidence_ledger import EvidenceLedger
from eai.axnode_sidecar_backup import create_sidecar_bundle, restore_sidecar_bundle


class SidecarBackupTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.root=self.base/"original"
        self.store=AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        self.anchor=self.store.import_node(json.dumps({
            "schema":"eai.axnode.v1","id":"synthetic.anchor","version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"csv":"csv_ref"},"output":"difference_receipt"},
            "pre":["authorized_only"],"post":["independent_check_later"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":[],
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"EAI_DESIGN","source":"synthetic_only"},
            "budget":{"max_steps":2,"max_seconds":20},
        }))

    def make_sidecars(self):
        with AXNodeMemory(self.store) as memory:
            memory.remember(tier="EPISODIC",anchor_sha=self.anchor,
                            label="synthetic.review",captured_at=100)
        with EvidenceLedger(self.store,create=True) as evidence:
            evidence.append(claim_id="synthetic.review",
                            source_sha256=self.anchor,polarity="REFUTE",
                            observed_at=100,expires_at=200,now=150)

    def test_two_snapshots_and_isolated_recovery_preserve_original(self):
        self.make_sidecars()
        original={x:(self.root/x).read_bytes()
                  for x in ("axnode_memory.sqlite","evidence_ledger.sqlite")}
        zip_path=self.base/"backup.zip"
        with patch.object(socket,"socket",side_effect=AssertionError("network")):
            create_sidecar_bundle(self.store,zip_path)
            restored=restore_sidecar_bundle(zip_path,self.base/"quarantine")
        self.assertEqual(restored.name,"quarantine")
        self.assertEqual({p.name for p in restored.iterdir()},
                         {"memory.sqlite","evidence.sqlite",".eai-restore-complete.sha256"})
        self.assertEqual(original,{x:(self.root/x).read_bytes() for x in original})
        with sqlite3.connect(restored/"memory.sqlite") as db:
            self.assertEqual(db.execute("SELECT count(*) FROM entries").fetchone()[0],1)
        with sqlite3.connect(restored/"evidence.sqlite") as db:
            self.assertEqual(db.execute("SELECT count(*) FROM observations").fetchone()[0],1)

    def test_open_wal_writer_is_included_in_online_snapshot(self):
        with EvidenceLedger(self.store,create=True) as writer:
            writer.append(claim_id="synthetic.review",source_sha256=self.anchor,
                          polarity="SUPPORT",observed_at=100,expires_at=200,now=150)
            create_sidecar_bundle(self.store,self.base/"backup.zip")
        with zipfile.ZipFile(self.base/"backup.zip") as z:
            data=z.read("evidence.sqlite")
        stage=self.base/"snapshot.sqlite"
        stage.write_bytes(data)
        with sqlite3.connect(stage) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM observations").fetchone()[0],1)

    def test_no_sidecar_is_not_success(self):
        with self.assertRaisesRegex(ValueError,"no optional sidecars"):
            create_sidecar_bundle(self.store,self.base/"empty.zip")
        self.assertFalse((self.base/"empty.zip").exists())

    def test_refuse_to_overwrite_original_or_existing_backup(self):
        self.make_sidecars()
        archive=self.base/"backup.zip"
        create_sidecar_bundle(self.store,archive)
        before=archive.read_bytes()
        with self.assertRaises(FileExistsError):
            create_sidecar_bundle(self.store,archive)
        self.assertEqual(archive.read_bytes(),before)
        target=self.base/"existing"
        target.mkdir()
        keep=target/"keep.txt"
        keep.write_text("original",encoding="utf-8")
        with self.assertRaises(FileExistsError):
            restore_sidecar_bundle(archive,target)
        self.assertEqual(keep.read_text(encoding="utf-8"),"original")

    def test_reject_archive_modification_before_restore_root_exists(self):
        self.make_sidecars()
        good=self.base/"good.zip"
        create_sidecar_bundle(self.store,good)
        bad=self.base/"bad.zip"
        with zipfile.ZipFile(good) as src,zipfile.ZipFile(bad,"w") as out:
            for info in src.infolist():
                content=src.read(info.filename)
                if info.filename=="memory.sqlite":
                    content+=b"forged"
                out.writestr(info.filename,content,compress_type=zipfile.ZIP_STORED)
        restored=self.base/"must-not-exist"
        with self.assertRaisesRegex(ValueError,"modified"):
            restore_sidecar_bundle(bad,restored)
        self.assertFalse(restored.exists())

    def test_reject_zip_traversal_and_duplicate_names(self):
        dest=self.base/"target"
        bad=self.base/"traversal.zip"
        with zipfile.ZipFile(bad,"w") as z:
            z.writestr("manifest.json","{}")
            z.writestr("../outside.txt","bad")
        with self.assertRaises(ValueError):
            restore_sidecar_bundle(bad,dest)
        self.assertFalse(dest.exists())

    def test_corrupt_sidecar_does_not_get_snapshot_or_deleted(self):
        (self.root/"evidence_ledger.sqlite").write_bytes(b"broken")
        with self.assertRaises((ValueError,sqlite3.DatabaseError)):
            create_sidecar_bundle(self.store,self.base/"bad.zip")
        self.assertEqual((self.root/"evidence_ledger.sqlite").read_bytes(),b"broken")
        self.assertFalse((self.base/"bad.zip").exists())

    def test_reject_forged_sidecar_index_metadata(self):
        with AXNodeMemory(self.store) as memory:
            memory.remember(tier="EPISODIC",anchor_sha=self.anchor,
                            label="synthetic.review",captured_at=100)
        with sqlite3.connect(self.root/"axnode_memory.sqlite") as db:
            db.execute("UPDATE entries SET label='forged'")
        with self.assertRaisesRegex(ValueError,"metadata mismatch"):
            create_sidecar_bundle(self.store,self.base/"forged.zip")
        self.assertFalse((self.base/"forged.zip").exists())

    def test_backup_archive_permissions_are_private_where_supported(self):
        import os
        self.make_sidecars()
        archive=self.base/"private.zip"
        create_sidecar_bundle(self.store,archive)
        if os.name == "posix":
            self.assertEqual(archive.stat().st_mode & 0o077,0)
        self.assertGreater(archive.stat().st_size,0)

    def test_incomplete_restore_has_no_success_marker(self):
        self.make_sidecars()
        archive=self.base/"incomplete.zip"
        create_sidecar_bundle(self.store,archive)
        import os
        target=self.base/"interrupted"
        original=os.link
        calls=[0]
        def stop_midway(src,dest,*args,**kwargs):
            if Path(dest).parent==target:
                calls[0]+=1
                if calls[0]==2:
                    raise OSError("synthetic crash during second file publication")
            return original(src,dest,*args,**kwargs)
        with patch("eai.axnode_sidecar_backup.os.link",side_effect=stop_midway):
            with self.assertRaisesRegex(OSError,"synthetic crash"):
                restore_sidecar_bundle(archive,target)
        self.assertTrue(target.is_dir())
        self.assertFalse((target/".eai-restore-complete.sha256").exists())
        self.assertEqual((target/"evidence.sqlite").exists()+
                         (target/"memory.sqlite").exists(),1)
        self.assertTrue(archive.exists())

    def test_active_store_location_rejected_for_archive(self):
        self.make_sidecars()
        with self.assertRaisesRegex(ValueError,"inside active"):
            create_sidecar_bundle(self.store,self.root/"backup.zip")


if __name__=="__main__":
    unittest.main()
