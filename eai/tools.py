"""Versioned reusable tool registry and a local SearXNG search adapter."""
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit
from .network import fetch_json, local_base_url


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, object] = {}

    def register(self, name: str, tool: object) -> None:
        if not name or name in self._tools:
            raise ValueError("tool ID must be unique and nonempty")
        self._tools[name] = tool

    def get(self, name: str) -> object:
        return self._tools[name]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))


class SearxNGSearch:
    """Talk only to an explicitly configured local SearXNG JSON endpoint."""

    def __init__(self, url: str):
        self.base_url = local_base_url(url)

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        if not query.strip() or len(query) > 500 or not 1 <= limit <= 8:
            raise ValueError("invalid search query or limit")
        url = self.base_url + "/search?" + urlencode(
            {"q": query, "format": "json", "language": "auto"}
        )
        data = fetch_json(url, timeout=15.0)
        results = data.get("results", [])
        if not isinstance(results, list):
            raise ValueError("invalid search results")
        hits: list[SearchHit] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            source_url = row.get("url", "")
            if not isinstance(source_url, str) or len(source_url) > 2048:
                continue
            try:
                parts = urlsplit(source_url)
                if (parts.scheme not in {"https", "http"} or not parts.hostname
                        or parts.username or parts.password):
                    continue
            except ValueError:
                continue
            title = row.get("title", "")
            snippet = row.get("content", "")
            hits.append(SearchHit(
                str(title)[:200], source_url[:2048], str(snippet)[:1500]
            ))
            if len(hits) == limit:
                break
        return hits
