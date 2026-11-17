"""Pure OFFLINE AXNODE v1 parser: no storage, imports, eval or execution.

Import only DRAFT/CANDIDATE. A separate future verifier/store must promote
verified nodes and enforce cross-file parent graph acyclicity and provenance.
"""
from dataclasses import dataclass
import hashlib
import re

from .contracts import canonical_bytes, strict_json

AXNODE_SCHEMA = "eai.axnode.v1"
MAX_NODE_BYTES = 32 * 1024
NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
SAFE_SKILLS = frozenset({
    "csv.sha256.v1", "csv.reconcile.v1", "csv.diagnose.v1",
    "csv.schema_inspect.v1", "evidence.verify_receipt.v1"
})
SAFE_TYPES = frozenset({"csv_ref", "column", "difference_receipt", "receipt_ref",
                        "text", "number", "boolean", "list", "source_ref"})
SAFE_CAPABILITIES = frozenset({"pure", "local.read"})
_FIELDS = frozenset({
    "schema", "id", "version", "kind", "status", "signature", "pre",
    "post", "steps", "capabilities", "parent_hashes", "tests",
    "evidence", "provenance", "budget"
})


def _fail_if_not_dict(raw, keys):
    if type(raw) is not dict or set(raw) != set(keys):
        raise ValueError("invalid AXNODE fields")


def _id(value):
    if type(value) is not str or not NAME.fullmatch(value):
        raise ValueError("invalid AXNODE identifier")
    return value


def _text(value, limit=256):
    if type(value) is not str or not 1 <= len(value) <= limit or "\x00" in value:
        raise ValueError("invalid AXNODE text")
    return value


def _list(raw, *, limit=24, kind="text", unique=True):
    if type(raw) is not list or len(raw) > limit:
        raise ValueError("invalid AXNODE array")
    parsed = []
    for value in raw:
        if kind == "identifier":
            parsed.append(_id(value))
        elif kind == "hash":
            if type(value) is not str or not HASH.fullmatch(value):
                raise ValueError("invalid AXNODE parent digest")
            parsed.append(value)
        else:
            parsed.append(_text(value))
    if unique and len(set(parsed)) != len(parsed):
        raise ValueError("duplicate AXNODE array item")
    return parsed


@dataclass(frozen=True)
class AXNode:
    canonical: bytes
    sha256: str

    def as_dict(self) -> dict:
        """Return fresh data, never expose shared mutable live storage."""
        return strict_json(self.canonical)


def parse_axnode(data: str | bytes) -> AXNode:
    raw = strict_json(data, max_bytes=MAX_NODE_BYTES)
    _fail_if_not_dict(raw, _FIELDS)
    if (raw["schema"] != AXNODE_SCHEMA or type(raw["schema"]) is not str
            or type(raw["version"]) is not int or raw["version"] != 1
            or raw["kind"] != "strategy" or type(raw["kind"]) is not str
            or type(raw["status"]) is not str
            or raw["status"] not in ("DRAFT", "CANDIDATE")):
        raise ValueError("unsupported or promoted AXNODE cannot be imported")
    _id(raw["id"])
    sig = raw["signature"]
    _fail_if_not_dict(sig, {"inputs", "output"})
    inputs = sig["inputs"]
    if type(inputs) is not dict or not 1 <= len(inputs) <= 16:
        raise ValueError("invalid AXNODE signature inputs")
    for key, value in inputs.items():
        if _id(key) != key or type(value) is not str or value not in SAFE_TYPES:
            raise ValueError("unknown AXNODE input type")
    if type(sig["output"]) is not str or sig["output"] not in SAFE_TYPES:
        raise ValueError("unknown AXNODE output type")

    _list(raw["pre"], limit=20)
    _list(raw["post"], limit=20)
    steps = raw["steps"]
    if type(steps) is not list or not 1 <= len(steps) <= 12:
        raise ValueError("invalid AXNODE step count")
    for step in steps:
        _fail_if_not_dict(step, {"skill"})
        if type(step["skill"]) is not str or step["skill"] not in SAFE_SKILLS:
            raise ValueError("unapproved AXNODE skill")

    capabilities = _list(raw["capabilities"], limit=2, kind="identifier")
    if not set(capabilities) <= SAFE_CAPABILITIES:
        raise ValueError("AXNODE privilege escalation denied")
    parents = _list(raw["parent_hashes"], limit=12, kind="hash")
    tests = raw["tests"]
    _fail_if_not_dict(tests, {"unit", "heldout", "negative"})
    for name in ("unit", "heldout", "negative"):
        _list(tests[name], limit=24, kind="identifier")
    if raw["evidence"] != [] or type(raw["evidence"]) is not list:
        raise ValueError("unverified AXNODE cannot supply evidence receipts")

    prov = raw["provenance"]
    _fail_if_not_dict(prov, {"author", "source"})
    _id(prov["author"].lower())
    _id(prov["source"])
    budget = raw["budget"]
    _fail_if_not_dict(budget, {"max_steps", "max_seconds"})
    count, seconds = budget["max_steps"], budget["max_seconds"]
    if (type(count) is not int or not 1 <= count <= 12
            or count < len(steps) or type(seconds) is not int
            or not 1 <= seconds <= 300):
        raise ValueError("unbounded AXNODE budget")
    canonical = canonical_bytes(raw)
    if len(canonical) > MAX_NODE_BYTES:
        raise ValueError("canonical AXNODE too large")
    digest = hashlib.sha256(canonical).hexdigest()
    if digest in parents:
        raise ValueError("self-parent AXNODE forbidden")
    return AXNode(canonical, digest)
