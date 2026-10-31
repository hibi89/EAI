"""Real localhost HTTP integration, with fake Ollama/SearXNG only (no external data)."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError

from eai.intent import QwenIntentParser
from eai.runner import EAIRunner
from eai.storage import Store
from eai.tools import SearxNGSearch


@contextmanager
def fake_local_server(redirect=False):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            if self.path != '/api/chat':
                self.send_error(404)
                return
            size = int(self.headers.get('Content-Length', '0'))
            data = json.loads(self.rfile.read(size).decode('utf-8'))
            requests.append(('ollama', data))
            if redirect:
                self.send_response(302)
                self.send_header('Location', 'https://example.org/forbidden')
                self.end_headers()
                return
            body = {'message': {'content': json.dumps(dict(
                version=1, task='calculate', expression='6*7', query=''
            ))}}
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if not self.path.startswith('/search?'):
                self.send_error(404)
                return
            requests.append(('search', self.path))
            if redirect:
                self.send_response(302)
                self.send_header('Location', 'https://example.org/forbidden')
                self.end_headers()
                return
            body = {'results': [{'title': 'Official example',
                                 'url': 'https://example.org/release',
                                 'content': 'Example release notes'}]}
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', requests
    finally:
        server.shutdown()
        t.join(timeout=3)
        server.server_close()


class LocalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'memory.db')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_ollama_structured_input_only_over_real_local_http(self):
        with fake_local_server() as (url, requests):
            parser = QwenIntentParser(model='fake-local-qwen', url=url, profile='CPU_ECO')
            output = EAIRunner(self.store, parser=parser).ask('7 곱하기 6은?')
        self.assertEqual(output.result.data['value'], '42')
        self.assertEqual(len(requests), 1)
        msg = requests[0][1]
        self.assertEqual(msg['options']['num_gpu'], 0)
        self.assertIn('format', msg)
        self.assertEqual(len(msg['messages']), 2)
        self.assertEqual(len(self.store.recent_turns()), 2)

    def test_searxng_live_loopback_cached_and_offline_denied(self):
        with fake_local_server() as (url, requests):
            search = SearxNGSearch(url)
            runner = EAIRunner(self.store, search_tool=search)
            one = runner.ask('검색 local release', allow_online=True)
            two = runner.ask('검색 local release', allow_online=True)
            denied = runner.ask('검색 different query', allow_online=False)
        self.assertEqual(one.result.status, 'OK')
        self.assertTrue(two.result.cache_hit)
        self.assertEqual(denied.result.status, 'UNAVAILABLE')
        self.assertEqual([kind for kind, _ in requests], ['search'])
        self.assertIn('원문 미검증', one.text)

    def test_http_redirects_never_followed(self):
        with fake_local_server(redirect=True) as (url, requests):
            one = EAIRunner(self.store, search_tool=SearxNGSearch(url)).ask(
                '검색 redirect trial', allow_online=True)
            self.assertEqual(one.result.status, 'UNAVAILABLE')
            self.assertIn('온라인 조회 실패', one.text)
            self.assertEqual(len(requests), 1)
            with self.assertRaises(HTTPError):
                QwenIntentParser(url=url).parse('계산 1+1')
            self.assertEqual(len(requests), 2)


if __name__ == '__main__':
    unittest.main()
