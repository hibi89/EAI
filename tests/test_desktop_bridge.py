"""Safe local GUI->bridge acceptance probes; no Tk display or live services."""
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from eai.desktop_bridge import DesktopBridge


class DesktopBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = DesktopBridge(self.root / 'private')

    def test_unsupported_natural_request_holds_without_creating_database(self):
        result = self.bridge.ask('내 컴퓨터에서 모든 작업을 자동으로 실행해줘')
        self.assertEqual(result['status'], 'HOLD_UNSUPPORTED_REQUEST')
        self.assertEqual(result['external_calls'], 0)
        self.assertFalse(self.bridge.state_root.exists())

    def test_note_needs_separate_explicit_consent(self):
        result = self.bridge.ask('기억해: 안전한 로컬 메모')
        self.assertEqual(result['status'], 'HOLD_EXPLICIT_NOTE_APPROVAL')
        self.assertFalse(self.bridge.state_root.exists())

    def test_search_is_inert_without_online_opt_in(self):
        result = self.bridge.ask('검색: 외부 웹 검색')
        self.assertEqual(result['status'], 'HOLD_NO_REMOTE_OR_LOCAL_SEARCH_CONFIGURED')
        self.assertEqual(result['external_calls'], 0)

    def test_draft_validation_and_exclusive_save(self):
        raw = self.bridge.make_problem_draft('리소스 제약을 평가해줘')
        self.assertEqual(raw['permissions'], ['pure'])
        self.assertEqual(raw['risk'], 'MEDIUM')
        path = self.bridge.save_new_draft(raw)
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), raw)
        with self.assertRaises(FileExistsError):
            self.bridge.save_new_draft(raw)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), raw)

    def test_no_unchecked_file_path_in_catalog(self):
        with self.assertRaises(ValueError):
            self.bridge.axnode_catalog(self.root / 'not-present')

    def test_catalog_is_read_only_and_bounded(self):
        store = self.root / 'axnodes'
        (store / 'nodes').mkdir(parents=True)
        sha = 'a' * 64
        with sqlite3.connect(store / 'axnodes.sqlite') as db:
            db.executescript('''
                CREATE TABLE nodes(sha256 TEXT PRIMARY KEY, node_id TEXT,
                  version INTEGER, status TEXT, kind TEXT, output_type TEXT,
                  search_text TEXT);
                CREATE TABLE parents(child_sha TEXT,parent_sha TEXT);
                PRAGMA user_version=1;
            ''')
            db.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',
                       (sha, 'node_sample', 1, 'CANDIDATE', 'logic', 'text', 'node_sample'))
            db.commit()
        before = (store / 'axnodes.sqlite').read_bytes()
        result = self.bridge.axnode_catalog(store, query='sample')
        self.assertEqual(result['status'], 'LOCAL_CATALOG_UNVERIFIED')
        self.assertEqual(result['total_nodes'], 1)
        self.assertEqual(result['nodes'][0]['sha256'], sha)
        self.assertEqual((store / 'axnodes.sqlite').read_bytes(), before)
        with self.assertRaises(ValueError):
            self.bridge.axnode_catalog(store, query='x' * 121)

    def test_no_player_execution_without_explicit_simulation_consent(self):
        result = self.bridge.player('absent', 'absent')
        self.assertEqual(result['status'], 'HOLD_PURE_SIMULATION_CONFIRMATION')
        self.assertEqual(result['execution'], 'NOT_EXECUTED')


if __name__ == '__main__':
    unittest.main()
