"""Contract and offline functional tests for EAI-owned intelligence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eai.network import fetch_json, local_base_url

from eai.intent import IntentSpec, RuleIntentParser, QwenIntentParser, INTENT_SCHEMA
from eai.cognition import CognitiveEngine, ResponseEngine, exact_calculate
from eai.runner import EAIRunner
from eai.storage import Store
from eai.tools import SearchHit, SearxNGSearch, ToolRegistry


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
        self.assertFalse(result.parser_fallback)  # explicit calculation never invokes Qwen
        self.assertEqual(result.result.data['value'], '7')
        unclear = EAIRunner(self.store, parser=BrokenParser()).ask('10 빼기 3은?')
        self.assertTrue(unclear.parser_fallback)
        self.assertEqual(unclear.result.status, 'UNSUPPORTED')

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
        self.assertIn('계산·수치 비교·검색·기억', result.text)

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

    def test_fetch_json_denies_remote_and_ambiguous_urls_before_transport(self):
        invalid = (
            "http://example.org:8000/ingest",
            "https://127.0.0.1:8080/api",
            "http://user@localhost:8080/api",
            "http://localhost:8080#fragment",
            "http://localhost:0/api",
            "http://localhost:99999/api",
            "http://localhost/api",
            "http://2130706433:8080/api",
            "http://[::1]:8080/api",
            "http://localhost:8080//other-host/path",
            "http://localhost:8080/ok\r\nInjected: yes",
            " http://127.0.0.1:8080/api",
            "http://127.0.0.1:8080/api ",
        )
        with patch("eai.network.build_opener",
                   side_effect=AssertionError("transport must not open")):
            for url in invalid:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    fetch_json(url)
            for timeout in (0, -1, True, float("nan"), float("inf"), 121):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    fetch_json("http://127.0.0.1:11434/api", timeout=timeout)
            with self.assertRaises(ValueError):
                fetch_json("http://127.0.0.1:11434/api", payload={"a": "x" * 1_048_577})
            with self.assertRaises(ValueError):
                fetch_json("http://127.0.0.1:11434/api", payload={"a": float("nan")})

    def test_fetch_json_pins_localhost_to_numeric_loopback_and_preserves_host(self):
        class Response:
            headers = {"Content-Length": "12"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, limit):
                self.assert_limit = limit
                return b'{"ok": true}'

        class Opener:
            requests = []

            def open(self, request, timeout):
                self.requests.append((request, timeout))
                return Response()

        opener = Opener()
        with patch("eai.network.build_opener", return_value=opener) as builder:
            output = fetch_json("http://localhost:8080/search?q=korean", timeout=4.0)
        self.assertEqual(output, {"ok": True})
        self.assertEqual(len(opener.requests), 1)
        request, timeout = opener.requests[0]
        self.assertEqual(timeout, 4.0)
        self.assertEqual(request.full_url,
                         "http://127.0.0.1:8080/search?q=korean")
        self.assertEqual(request.get_header("Host"), "localhost:8080")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(len(builder.call_args.args), 2)
        from urllib.request import HTTPRedirectHandler, ProxyHandler
        self.assertIsInstance(builder.call_args.args[0], ProxyHandler)
        self.assertEqual(builder.call_args.args[0].proxies, {})
        redirect_handler = builder.call_args.args[1]
        self.assertTrue(issubclass(redirect_handler, HTTPRedirectHandler))
        self.assertEqual(redirect_handler.__name__, "NoRedirect")
        self.assertIsNone(redirect_handler().redirect_request(
            None, None, 302, "", {}, "https://example.org/blocked"))

    def test_searx_mock_parsing(self):
        with patch('eai.tools.fetch_json', return_value={'results': [
            {'title': 'A', 'url': 'https://example.org', 'content': 'a'},
            {'title': 'bad', 'url': 'file:///private', 'content': 'b'},
        ]}):
            hits = SearxNGSearch('http://localhost:8080').search('q')
        self.assertEqual(len(hits), 1)


if __name__ == '__main__':
    unittest.main()
