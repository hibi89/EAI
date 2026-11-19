"""Bounded loopback-only HTTP client for Ollama and local SearXNG."""
import json
import math
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler


MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BYTES = 1_048_576
_MAX_ENDPOINT_CHARS = 4_096


def _reject_duplicate_json_fields(pairs: list[tuple[str, object]]) -> dict:
    """Model and search responses are untrusted; never accept shadowed fields."""
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("duplicate fields in local JSON response")
        values[key] = value
    return values


def _reject_nonfinite_json(_value: str) -> None:
    raise ValueError("nonfinite local JSON response value")


def _pinned_loopback_endpoint(url: str) -> tuple[str, str]:
    """Check the final request URL, never trust a caller's base URL check.

    All transport goes to literal 127.0.0.1 even if the local hosts file or
    DNS falsely resolves "localhost" to a remote machine. Preserve the
    original local HTTP Host header for a loopback virtual host.
    """
    if (type(url) is not str or not 1 <= len(url) <= _MAX_ENDPOINT_CHARS
            or any(char.isspace() or ord(char) == 127 for char in url)):
        raise ValueError("invalid local HTTP endpoint")
    try:
        parts = urlsplit(url)
        port = parts.port
        host = parts.hostname
    except ValueError as exc:
        raise ValueError("invalid local HTTP endpoint") from exc
    if (parts.scheme != "http" or host not in {"localhost", "127.0.0.1"}
            or parts.username is not None or parts.password is not None
            or port is None or port == 0 or parts.fragment
            or parts.netloc != f"{host}:{port}"
            or parts.path.startswith("//")):
        raise ValueError("only canonical loopback HTTP endpoints are permitted")
    pinned = urlunsplit(("http", f"127.0.0.1:{port}",
                         parts.path, parts.query, ""))
    return pinned, parts.netloc



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
    pinned_url, host_header = _pinned_loopback_endpoint(url)
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 120):
        raise ValueError("invalid bounded local HTTP timeout")
    try:
        body = (json.dumps(payload, ensure_ascii=False, allow_nan=False)
                .encode("utf-8") if payload is not None else None)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid local HTTP JSON request") from exc
    if body is not None and len(body) > MAX_REQUEST_BYTES:
        raise ValueError("local HTTP request exceeds byte limit")
    request = Request(
        pinned_url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "User-Agent": "EAI-local/0.1", "Host": host_header},
        method="POST" if body is not None else "GET",
    )
    with build_opener(ProxyHandler({}), NoRedirect).open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > MAX_RESPONSE_BYTES:
            raise ValueError("response exceeds maximum size")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response exceeds maximum size")
        try:
            parsed = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_json_fields,
                parse_constant=_reject_nonfinite_json,
            )
        except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("invalid local JSON response") from exc
    if type(parsed) is not dict:
        raise ValueError("expected JSON object response")
    return parsed
