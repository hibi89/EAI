"""Contract and offline functional tests for EAI-owned intelligence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eai.intent import IntentSpec, RuleIntentParser, QwenIntentParser, INTENT_SCHEMA
from eai.cognition import CognitiveEngine, ResponseEngine, exact_calculate
from eai.runner import EAIRunner
from eai.storage import Store
from eai.tools import SearchHit, SearxNGSearch, ToolRegistry
from eai.network import local_base_url


class FakeSearch:
    def __init__(self, fail=False):
        self.count = 0
        self.fail = fail
    def search(self, query, limit=5):
        self.count += 1
        if self.fail:
            raise TimeoutError('offline')
        return [SearchHit('Official notes', 'https://example.org/release', 'A model release')]


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'store.sqlite'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_rule_calc_exact(self):
        a = EAIRunner(self.store).ask('계산 12*(3+4)')
        self.assertEqual(a.result.data['value'], '84')
        self.assertIn('84', a.text)

    def test_decimal_and_fraction(self):
        self.assertEqual(exact_calculate('0.1 + 0.2'), '0.3')
        self.assertEqual(exact_calculate('2/4'), '0.5')
        self.assertTrue(exact_calculate('1/3').startswith('0.333333'))

    def test_reject_unsafe_math(self):
        for expression in ['__import__("os")', '2**500000', '1/0', '9' * 200,
                           '[1,2][0]', '2 // 1', '(1+2j)', '1e100000']:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                exact_calculate(expression)

    def test_spec_strict(self):
        base = dict(version=1, task='calculate', expression='2+2', query='')
        self.assertEqual(IntentSpec.validate(base).task, 'calculate')
        for bad in [dict(base, extra='exfiltrate'), dict(base, version=True),
                    dict(base, task='shell'), dict(base, expression=''),
                    dict(base, task='search', query='')]:
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                IntentSpec.validate(bad)

    def test_qwen_input_only_contract(self):
        parser = QwenIntentParser(profile='CPU_ECO')
        data = {'message': {'content': json.dumps(dict(version=1, task='calculate', expression='3*9', query=''))}}
        with patch('eai.intent.fetch_json', return_value=data) as mocked:
            spec = parser.parse('계산 3 곱하기 9')
        self.assertEqual(spec.expression, '3*9')
        payload = mocked.call_args.kwargs['payload']
        self.assertEqual(payload['format'], INTENT_SCHEMA)
        self.assertEqual(payload['options']['num_gpu'], 0)
        self.assertEqual(len(payload['messages']), 2)
        self.assertNotIn('retrieved sources', str(payload).lower())
        self.assertNotIn('calculate a result', payload['messages'][0]['content'].lower())

    def test_qwen_invalid_json_rejected(self):
        parser = QwenIntentParser()
        with patch('eai.intent.fetch_json', return_value={'message': {'content': 'wrong'}}):
            with self.assertRaises(ValueError):
                parser.parse('calculate 2+2')

    def test_no_llm_answer_when_parsing_fails(self):
        class BrokenParser:
            def parse(self, question): raise OSError('Qwen down')
        result = EAIRunner(self.store, parser=BrokenParser()).ask('계산 10-3')
        self.assertTrue(result.parser_fallback)
        self.assertEqual(result.result.data['value'], '7')

    def test_qwen_parser_not_used_for_answer(self):
        class SpyParser:
            calls = 0
            def parse(self, text):
                self.calls += 1
                return IntentSpec('calculate', expression='7*6')
        spy = SpyParser()
        result = EAIRunner(self.store, parser=spy).ask('42 확인')
        self.assertEqual(spy.calls, 1)
        self.assertEqual(result.result.data['value'], '42')
        self.assertIn('42', result.text)

    def test_unsupported_task_no_hallucinated_answer(self):
        result = EAIRunner(self.store).ask('양자물리학을 자세히 설명해 줘')
        self.assertEqual(result.result.status, 'UNSUPPORTED')
        self.assertIn('계산·검색·기억', result.text)

    def test_persistence_after_restart(self):
        runner = EAIRunner(self.store)
        runner.ask('계산 100/4')
        self.store.close()
        self.store = Store(self.path)
        turns = self.store.recent_turns()
        self.assertEqual(len(turns), 2)
        self.assertIn('25', turns[-1]['content'])

    def test_search_requires_consent(self):
        search = FakeSearch()
        answer = EAIRunner(self.store, search_tool=search).ask('검색 새로운 오픈소스 모델')
        self.assertEqual(answer.result.status, 'UNAVAILABLE')
        self.assertEqual(search.count, 0)

    def test_search_cache_hit(self):
        search = FakeSearch()
        runner = EAIRunner(self.store, search_tool=search)
        first = runner.ask('검색 새로운 오픈소스 모델', allow_online=True)
        second = runner.ask('검색 새로운 오픈소스 모델', allow_online=True)
        self.assertEqual(first.result.status, 'OK')
        self.assertTrue(second.result.cache_hit)
        self.assertEqual(search.count, 1)
        self.assertIn('원문 미검증', second.text)

    def test_search_failure_warns(self):
        answer = EAIRunner(self.store, search_tool=FakeSearch(True)).ask('검색 뉴스', allow_online=True)
        self.assertEqual(answer.result.status, 'UNAVAILABLE')
        self.assertIn('온라인 조회 실패', answer.text)

    def test_recall_stored_documents(self):
        self.store.save_search('test', [SearchHit('Qwen model release', 'https://example.org', 'Qwen notes')])
        answer = EAIRunner(self.store).ask('기억 Qwen')
        self.assertEqual(answer.result.status, 'OK')
        self.assertIn('Qwen model release', answer.text)

    def test_invalid_question_no_record(self):
        with self.assertRaises(ValueError): EAIRunner(self.store).ask('')
        self.assertEqual(self.store.recent_turns(), [])

    def test_health_no_network_is_separate_cli(self):
        self.assertEqual(RuleIntentParser().parse('도움말').task, 'help')
        self.assertEqual(RuleIntentParser().parse('알고리즘 설명').task, 'unsupported')

    def test_only_loopback(self):
        self.assertEqual(local_base_url('http://127.0.0.1:11434'), 'http://127.0.0.1:11434')
        for invalid in ['https://127.0.0.1:11434', 'http://example.org:8080',
                        'http://user:pass@localhost:8080', 'http://localhost:8080/x']:
            with self.assertRaises(ValueError): local_base_url(invalid)

    def test_searx_mock_parsing(self):
        with patch('eai.tools.fetch_json', return_value={'results': [
            {'title': 'A', 'url': 'https://example.org', 'content': 'a'},
            {'title': 'bad', 'url': 'file:///private', 'content': 'b'},
        ]}):
            hits = SearxNGSearch('http://localhost:8080').search('q')
        self.assertEqual(len(hits), 1)


if __name__ == '__main__':
    unittest.main()
