"""Ensure templates are fixed, reusable and cannot bypass online consent."""
import unittest
from eai.tools import SearchHit, ToolRegistry
from eai.workflows import WorkflowRegistry


class DummySearch:
    def __init__(self):
        self.queries = []

    def search(self, query, limit=5):
        self.queries.append((query, limit))
        return [SearchHit("test", "https://example.org", "text")]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.search = DummySearch()
        self.registry.register("web.search.v1", self.search)
        self.workflows = WorkflowRegistry()

    def test_reusable_bounded_template(self):
        self.assertEqual(self.workflows.names(), ("research.web.v1",))
        first = self.workflows.execute(
            "research.web.v1", self.registry, "Qwen", allow_online=True
        )
        second = self.workflows.execute(
            "research.web.v1", self.registry, "Ollama", allow_online=True
        )
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(self.search.queries, [("Qwen", 5), ("Ollama", 5)])

    def test_without_permission_no_side_effects(self):
        with self.assertRaises(PermissionError):
            self.workflows.execute("research.web.v1", self.registry, "secret")
        self.assertEqual(self.search.queries, [])

    def test_unknown_template_fails_closed(self):
        with self.assertRaises(KeyError):
            self.workflows.execute("arbitrary.shell.v1", self.registry, "test", allow_online=True)
        self.assertEqual(self.search.queries, [])


if __name__ == "__main__":
    unittest.main()
