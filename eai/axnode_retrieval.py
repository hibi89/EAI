"""AXNODE V3 deterministic local retrieval: typed, lexical FTS5, parent graph.

Only DRAFT/CANDIDATE nodes are indexed. Retrieved documents are proposals,
not instructions, executable skills, verification or autonomous approvals.
"""
from dataclasses import dataclass
import re
import sqlite3

from .axnode_store import AXNodeStore
from .axnode_schema import SAFE_TYPES
from .axnode_memory import AXNodeMemory
from .axnode_memory_review import review_memory_reuse

_TERM = re.compile(r"[\w가-힣]{1,40}", re.UNICODE)
_MAX_LOOKUP = 3000


@dataclass(frozen=True)
class NodeMatch:
    sha256: str
    node_id: str
    kind: str
    status: str
    output_type: str
    score: int
    parents: tuple[str, ...]
    provenance: str = "LOCAL_CANDIDATE_UNVERIFIED"


class AXNodeRetriever:
    """Local search; never constructs network queries or runs node steps."""

    def __init__(self, store: AXNodeStore):
        if type(store) is not AXNodeStore:
            raise ValueError("AXNODE retriever needs an explicit local store")
        self.store = store
        self.fts_enabled = False
        # A search index is reconstructible: never remove the source of truth.
        try:
            with self.store.db:
                self.store.db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS axnode_fts "
                    "USING fts5(sha256 UNINDEXED, search_text)"
                )
                self.store.db.execute(
                    "CREATE TRIGGER IF NOT EXISTS axnode_fts_add "
                    "AFTER INSERT ON nodes BEGIN "
                    "INSERT INTO axnode_fts(sha256,search_text) "
                    "VALUES(new.sha256,new.search_text); END"
                )
                self.store.db.execute("DELETE FROM axnode_fts")
                self.store.db.execute(
                    "INSERT INTO axnode_fts(sha256,search_text) "
                    "SELECT sha256,search_text FROM nodes"
                )
            self.fts_enabled = True
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" not in str(exc).lower():
                raise
            # Compatible with older SQLite builds: slower, bounded LIKE fallback.

    @staticmethod
    def _tokens(query: str) -> list[str]:
        if type(query) is not str or len(query) > 300 or "\x00" in query:
            raise ValueError("invalid AXNODE lookup")
        return list(dict.fromkeys(
            _TERM.findall(query.casefold())[:8]
        ))

    def find(self, query: str, *, output_type: str | None = None,
             related_to: str | None = None, limit: int = 8,
             memory: AXNodeMemory | None = None,
             withdrawn_hashes: tuple[str, ...] = (),
             now: int | None = None) -> tuple[NodeMatch, ...]:
        if type(limit) is not int or not 1 <= limit <= 25:
            raise ValueError("invalid AXNODE result limit")
        if output_type is not None and (type(output_type) is not str or output_type not in SAFE_TYPES):
            raise ValueError("unknown AXNODE type filter")
        if memory is not None and (type(memory) is not AXNodeMemory
                                   or memory.store is not self.store):
            raise ValueError("negative review must use the same local AXNODE store")
        if (type(withdrawn_hashes) is not tuple or len(withdrawn_hashes) > 32
                or len(set(withdrawn_hashes)) != len(withdrawn_hashes)):
            raise ValueError("bounded withdrawn source list required")
        for digest in withdrawn_hashes:
            self.store.get(digest)
        tokens = self._tokens(query)
        if not tokens and related_to is None:
            return ()
        adjacent: set[str] = set()
        if related_to is not None:
            # Verifies the reference exists and is hash-pinned.
            self.store.get(related_to)
            adjacent.update(self.store.parents_of(related_to))
            adjacent.update(self.store.children_of(related_to))
            adjacent.add(related_to)

        candidates: set[str] = set(adjacent)
        if tokens and self.fts_enabled:
            # Quoted literal terms, never free-form MATCH syntax.
            phrase = " OR ".join('"' + term.replace('"', '""') + '"' for term in tokens)
            sql = "SELECT sha256 FROM axnode_fts WHERE axnode_fts MATCH ? LIMIT ?"
            try:
                candidates.update(row[0] for row in self.store.db.execute(
                    sql, (phrase, _MAX_LOOKUP)
                ))
            except sqlite3.OperationalError as exc:
                raise ValueError("invalid FTS search") from exc
        if tokens:
            # Substring fallback/recall for Korean compounds; bounded scan.
            # The source DB is local; no text is ever sent to an embedding API.
            rows = self.store.db.execute(
                "SELECT sha256,search_text FROM nodes ORDER BY node_id,version LIMIT ?",
                (_MAX_LOOKUP,)
            ).fetchall()
            for digest, words in rows:
                if any(t in words.casefold() for t in tokens):
                    candidates.add(digest)

        result = []
        for digest in sorted(candidates):
            row = self.store.db.execute(
                "SELECT node_id,kind,status,output_type,search_text "
                "FROM nodes WHERE sha256=?", (digest,)
            ).fetchone()
            if row is None:
                continue
            name, kind, status, output, haystack = row
            if output_type is not None and output != output_type:
                continue
            # Revalidate every hit against immutable on-disk bytes. DB text is
            # a search hint, not trusted content; tampering must fail closed.
            node = self.store.get(digest)
            raw = node.as_dict()
            if raw["id"] != name or raw["kind"] != kind or raw["status"] != status or (
                    raw["signature"]["output"] != output):
                raise ValueError("AXNODE search metadata/hash mismatch")
            if withdrawn_hashes:
                # A withdrawn ancestor is not an eligible proposal; neither
                # FTS scoring nor a strong query match can override lineage.
                visited, todo = set(), [digest]
                denied = False
                while todo:
                    current = todo.pop()
                    if current in visited:
                        continue
                    visited.add(current)
                    if len(visited) > _MAX_LOOKUP:
                        raise ValueError("AXNODE withdrawn lineage budget exceeded")
                    if current in withdrawn_hashes:
                        denied = True
                    todo.extend(self.store.parents_of(current))
                if denied:
                    continue
            if memory is not None:
                # Review the actual matched node id, not the broad domain query.
                # Negative records and contradicted observations cannot be
                # hidden by FTS ranking or the result limit.
                reviewed = review_memory_reuse(
                    memory, name, withdrawn_hashes=withdrawn_hashes,
                    now=now, limit=25)
                if any(r.disposition != "UNVERIFIED_CANDIDATE_ONLY"
                       and r.label == name for r in reviewed):
                    continue
            matching = sum(t in haystack.casefold() for t in tokens)
            connected = digest in adjacent
            score = (100 if name.casefold() == query.casefold().strip() else 0)
            score += (20 if tokens and all(t in haystack.casefold() for t in tokens) else 0)
            score += 5 * matching
            score += 12 if connected else 0
            score += 20 if related_to is not None and digest == related_to else 0
            if score == 0:
                continue
            result.append(NodeMatch(digest,name,kind,status,output,score,
                                    self.store.parents_of(digest)))
        return tuple(sorted(result, key=lambda x: (-x.score, x.node_id, x.sha256))[:limit])
