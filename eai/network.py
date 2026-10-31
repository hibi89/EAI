"""Bounded loopback-only HTTP client for Ollama and local SearXNG."""
import json
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler


MAX_RESPONSE_BYTES = 1_048_576


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_base_url(raw: str) -> str:
    """Deny remote endpoints, credentials, paths, fragments and unexpected schemes."""
    parts = urlsplit(raw)
    if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"}
            or parts.username or parts.password or parts.path not in {"", "/"}
            or parts.query or parts.fragment):
        raise ValueError("only a loopback http://host:port base URL is permitted")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("invalid port") from exc
    if not port:
        raise ValueError("an explicit port is required")
    return f"http://{parts.hostname}:{port}"


def fetch_json(url: str, *, payload: dict | None = None, timeout: float = 12.0) -> dict:
    """Read only a bounded JSON payload, without following redirects."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "EAI-local/0.1"},
        method="POST" if body is not None else "GET",
    )
    with build_opener(ProxyHandler({}), NoRedirect).open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > MAX_RESPONSE_BYTES:
            raise ValueError("response exceeds maximum size")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response exceeds maximum size")
        parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object response")
    return parsed
