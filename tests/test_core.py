"""Offline, deterministic unit and end-to-end tests (no external services)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eai.app import EAI
from eai.network import local_base_url
from eai.storage import Store
from eai.tools import SearchHit, SearxNGSearch, ToolRegistry


class FakeLLM:
    def __init__(self):
        self.messages = []

    def respond(self, messages):
        self.messages.append(messages)
        return "검증 가능한 자료를 기준으로 답하겠습니다."


class FakeSearch:
    def __init__(self, fail=False):
        self.count = 0
        self.fail = fail

    def search(self, query, limit=5):
        self.count += 1
        if self.fail:
            raise TimeoutError("offline")
        return [SearchHit("Official release", "https://example.org/release", "Public release notes")]


class EAITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "memory.sqlite3"
        self.store = Store(self.path)
        self.llm = FakeLLM()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_offline_chat_persists_and_restores(self):
        first = EAI(self.store, self.llm)
        answer = first.ask("파이썬이란?")
        self.assertIn("자료", answer.text)
        self.assertEqual(len(self.store.recent_turns()), 2)
        second = EAI(self.store, self.llm)
        second.ask("이어서 설명해줘")
        self.assertEqual(len(self.store.recent_turns()), 4)
        self.assertEqual(self.llm.messages[-1][1]["role"], "user")

    def test_freshness_without_approval_warns(self):
        answer = EAI(self.store, self.llm, FakeSearch()).ask("오늘 뉴스가 뭐야?")
        self.assertIn("not checked", answer.warning)
        self.assertFalse(answer.sources)

    def test_opt_in_search_cached(self):
        search = FakeSearch()
        eai = EAI(self.store, self.llm, search)
        answer = eai.ask("최신 Qwen", allow_online=True)
        self.assertEqual(len(answer.sources), 1)
        self.assertEqual(search.count, 1)
        again = eai.ask("최신 Qwen", allow_online=True)
        self.assertTrue(again.cache_hit)
        self.assertEqual(search.count, 1)
        self.assertEqual(self.store.recall("Official"), answer.sources)

    def test_online_failure_falls_back_with_warning(self):
        result = EAI(self.store, self.llm, FakeSearch(fail=True)).ask("오늘 뉴스", allow_online=True)
        self.assertIn("failed", result.warning.lower())

    def test_invalid_role_and_duplicate_tool(self):
        with self.assertRaises(ValueError):
            self.store.add_turn("system", "not allowed")
        registry = ToolRegistry()
        registry.register("x", object())
        with self.assertRaises(ValueError):
            registry.register("x", object())

    def test_only_loopback_network_endpoints(self):
        self.assertEqual(local_base_url("http://localhost:8080"), "http://localhost:8080")
        for url in [
            "https://localhost:8080", "http://example.com:8080",
            "http://127.0.0.1:8080/path", "http://user:pw@localhost:8080",
            "http://localhost:8080/?x=y", "http://localhost",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_base_url(url)

    def test_search_adapter_bounded_and_structured(self):
        payload = {"results": [
            {"title": "Result", "url": "https://example.org", "content": "Snippet"},
            {"title": "Bad", "url": "file:///secret", "content": "skip"},
        ]}
        with patch("eai.tools.fetch_json", return_value=payload) as mocked:
            result = SearxNGSearch("http://127.0.0.1:8080").search("python", limit=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Result")
        self.assertIn("format=json", mocked.call_args.args[0])

    def test_cache_expiry(self):
        hits = [SearchHit("a", "https://a.example", "b")]
        self.store.save_search("test", hits, ttl_seconds=3, now=100)
        self.assertEqual(self.store.read_search_cache("test", now=102), hits)
        self.assertIsNone(self.store.read_search_cache("test", now=103))

    def test_no_model_invocation_on_invalid_input(self):
        with self.assertRaises(ValueError):
            EAI(self.store, self.llm).ask("")
        self.assertEqual(self.llm.messages, [])

    def test_empty_search_does_not_claim_freshness(self):
        class EmptySearch:
            def search(self, query, limit=5):
                return []
        result = EAI(self.store, self.llm, EmptySearch()).ask("오늘 뉴스", allow_online=True)
        self.assertIn("no results", result.warning.lower())

    def test_cached_search_discloses_freshness_limit(self):
        search = FakeSearch()
        eai = EAI(self.store, self.llm, search)
        eai.ask("오늘 뉴스", allow_online=True)
        second = eai.ask("오늘 뉴스", allow_online=True)
        self.assertTrue(second.cache_hit)
        self.assertIn("not guaranteed", second.warning)

    def test_recall_escapes_sql_wildcards(self):
        self.store.save_search("a", [SearchHit("100% real", "https://example.org/a", "literal")])
        self.assertEqual(len(self.store.recall("100%")), 1)
        self.assertEqual(self.store.recall("100_"), [])


if __name__ == "__main__":
    unittest.main()
