"""Real local SQLite note lifecycle and model permission-isolation tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eai.cognition import CognitiveEngine
from eai.intent import IntentSpec, RuleIntentParser, QwenIntentParser
from eai.runner import EAIRunner
from eai.storage import Store


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'eai.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_record_then_search_and_list(self):
        r = EAIRunner(self.store)
        a = r.ask('기억해: EAI는 CPU 중심 독립 엔진이다.')
        self.assertEqual(a.result.status, 'OK')
        self.assertEqual(a.result.data['note_id'], 1)
        self.assertIn('저장됨', a.text)
        self.assertIn('EAI', r.ask('기억검색 EAI').text)
        self.assertIn('EAI', r.ask('메모목록').text)

    def test_duplicate_is_idempotent(self):
        r = EAIRunner(self.store)
        r.ask('기억해 같은 데이터')
        dup = r.ask('기억해 같은 데이터')
        self.assertEqual(dup.result.data['note_id'], 1)
        self.assertFalse(dup.result.data['created'])
        self.assertEqual(len(self.store.list_notes()), 1)

    def test_persist_across_process_like_reopen(self):
        EAIRunner(self.store).ask('메모추가: 장기개발 로드맵')
        self.store.close()
        self.store = Store(self.path)
        self.assertIn('장기개발', EAIRunner(self.store).ask('기억 장기개발').text)
        self.assertEqual(self.store.list_notes()[0]['id'], 1)

    def test_model_must_not_authorize_storage(self):
        class BadParser:
            def parse(self, question):
                return IntentSpec('remember', query='injected model note')
        output = EAIRunner(self.store, parser=BadParser()).ask('아침 뉴스 알려줘')
        self.assertEqual(output.result.status, 'DENIED')
        self.assertEqual(self.store.list_notes(), [])

    def test_explicit_note_bypasses_model_entirely(self):
        class ExplodingParser:
            def parse(self, question):
                raise AssertionError('Qwen must not be called for explicit note writes')
        answer = EAIRunner(self.store, parser=ExplodingParser()).ask('기억해 비밀 내용은 로컬에만')
        self.assertEqual(answer.result.status, 'OK')
        self.assertEqual(self.store.list_notes()[0]['content'], '비밀 내용은 로컬에만')

    def test_no_network_even_if_search_enabled(self):
        class SearchSpy:
            def search(self, query, limit=5):
                raise AssertionError('note write must not invoke online search')
        answer = EAIRunner(self.store, search_tool=SearchSpy()).ask('메모추가 테스트', allow_online=True)
        self.assertEqual(answer.result.status, 'OK')

    def test_search_escapes_sql_wildcards_and_injection(self):
        self.store.add_note('CPU_100% 빠르게')
        self.store.add_note("x' OR 1=1 --")
        self.assertEqual(len(self.store.search_notes('%')), 1)
        self.assertEqual(len(self.store.search_notes('_')), 1)
        self.assertEqual(len(self.store.search_notes("x' OR 1=1 --")), 1)
        self.assertEqual(self.store.search_notes('does not exist'), [])

    def test_missing_notes_and_unknown_query(self):
        result = EAIRunner(self.store).ask('메모목록')
        self.assertIn('없습니다', result.text)
        self.assertEqual(self.store.search_notes('something'), [])

    def test_note_length_and_nul_rejected(self):
        for note in ('', 'x' * 2001, 'bad\x00payload'):
            with self.subTest(note_length=len(note)), self.assertRaises(ValueError):
                self.store.add_note(note)
        self.assertEqual(self.store.list_notes(), [])

    def test_intent_contract_note_write_and_search_bound(self):
        rules = RuleIntentParser()
        self.assertEqual(rules.parse('기억해: 새 사실').task, 'remember')
        self.assertEqual(rules.parse('메모추가 새 사실').task, 'remember')
        self.assertEqual(rules.parse('메모목록').task, 'notes')
        with self.assertRaises(ValueError):
            IntentSpec.validate(dict(version=1, task='search', expression='', query='x'*301))
        with self.assertRaises(ValueError):
            IntentSpec.validate(dict(version=1, task='remember', expression='', query='x'*2001))

    def test_source_evidence_not_confused_with_user_notes(self):
        from eai.tools import SearchHit
        self.store.save_search('original', [SearchHit('test page', 'https://example.com', 'snippet')])
        self.assertEqual(self.store.list_notes(), [])
        self.store.add_note('manually written')
        self.assertEqual(len(self.store.list_notes()), 1)
        self.assertEqual(len(self.store.recall('test')), 1)


if __name__ == '__main__':
    unittest.main()


class LegacyMigrationTests(unittest.TestCase):
    def test_existing_store_is_backed_up_before_notes_schema(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / 'original.sqlite3'
            with sqlite3.connect(db_path) as legacy:
                legacy.execute('CREATE TABLE turns (id INTEGER PRIMARY KEY, role TEXT, content TEXT, created_at INTEGER)')
                legacy.execute("INSERT INTO turns VALUES (1, 'user', 'original record', 1)")
            opened = Store(db_path)
            try:
                self.assertEqual(opened.recent_turns()[0]['content'], 'original record')
                self.assertEqual(opened.list_notes(), [])
                backups = list(Path(d).glob('original.sqlite3.pre-notes-*.bak'))
                self.assertEqual(len(backups), 1)
                with sqlite3.connect(backups[0]) as old:
                    self.assertEqual(old.execute('SELECT content FROM turns').fetchone()[0], 'original record')
                    self.assertIsNone(old.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_notes'"
                    ).fetchone())
            finally:
                opened.close()
