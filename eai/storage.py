"""Local SQLite conversation, search cache and unverified source memory."""
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from .tools import SearchHit


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=3000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_cache (
                cache_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                fetched_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                snippet TEXT NOT NULL,
                fetched_at INTEGER NOT NULL,
                evidence_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
            );
            CREATE TABLE IF NOT EXISTS user_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def recent_turns(self, limit: int = 6) -> list[dict[str, str]]:
        rows = self.db.execute(
            "SELECT role, content FROM turns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def add_turn(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("invalid conversation role")
        with self.db:
            self.db.execute(
                "INSERT INTO turns(role, content, created_at) VALUES (?, ?, ?)",
                (role, content[:20000], int(time.time())),
            )

    @staticmethod
    def _key(query: str) -> str:
        return hashlib.sha256(query.strip().casefold().encode("utf-8")).hexdigest()

    def read_search_cache(self, query: str, now: int | None = None) -> list[SearchHit] | None:
        stamp = int(time.time()) if now is None else now
        row = self.db.execute(
            "SELECT payload, expires_at FROM search_cache WHERE cache_key=?",
            (self._key(query),),
        ).fetchone()
        if row is None or row[1] <= stamp:
            return None
        return [SearchHit(**item) for item in json.loads(row[0])]

    def save_search(self, query: str, hits: list[SearchHit], ttl_seconds: int = 1800,
                    now: int | None = None) -> None:
        stamp = int(time.time()) if now is None else now
        if not 1 <= ttl_seconds <= 86400:
            raise ValueError("invalid cache TTL")
        payload = json.dumps([vars(hit) for hit in hits], ensure_ascii=False)
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?, ?)",
                (self._key(query), payload, stamp, stamp + ttl_seconds),
            )
            for hit in hits:
                self.db.execute(
                    "INSERT INTO documents(url, title, snippet, fetched_at, evidence_status) "
                    "VALUES (?, ?, ?, ?, 'UNVERIFIED') "
                    "ON CONFLICT(url) DO UPDATE SET title=excluded.title, "
                    "snippet=excluded.snippet, fetched_at=excluded.fetched_at, "
                    "evidence_status='UNVERIFIED'",
                    (hit.url, hit.title, hit.snippet, stamp),
                )

    def recall(self, query: str, limit: int = 3) -> list[SearchHit]:
        words = [w[:60] for w in query.strip().split() if len(w) >= 3][:5]
        if not words:
            return []
        conditions = " OR ".join("(title LIKE ? ESCAPE '!' OR snippet LIKE ? ESCAPE '!')" for _ in words)
        params: list[object] = []
        for word in words:
            pattern = "%" + word.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            params.extend([pattern, pattern])
        rows = self.db.execute(
            f"SELECT title, url, snippet FROM documents WHERE {conditions} "
            "ORDER BY fetched_at DESC LIMIT ?", (*params, limit)
        ).fetchall()
        return [SearchHit(*row) for row in rows]

    def add_note(self, content: str, now: int | None = None) -> tuple[int, bool]:
        """Explicit user note, local only, idempotent and additive (no overwrites)."""
        if not isinstance(content, str):
            raise ValueError('note content must be text')
        note = content.strip()
        if not 1 <= len(note) <= 2000 or '\x00' in note:
            raise ValueError('note must contain 1-2000 safe characters')
        digest = hashlib.sha256(note.encode('utf-8')).hexdigest()
        stamp = int(time.time()) if now is None else now
        with self.db:
            cur = self.db.execute(
                'INSERT OR IGNORE INTO user_notes(content_hash, content, created_at) VALUES (?, ?, ?)',
                (digest, note, stamp),
            )
            created = cur.rowcount == 1
            row = self.db.execute('SELECT id FROM user_notes WHERE content_hash=?', (digest,)).fetchone()
        return int(row[0]), created

    def search_notes(self, query: str, limit: int = 5) -> list[dict]:
        """Literal substring query; never interprets text as SQL or a command."""
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300 or not 1 <= limit <= 20:
            raise ValueError('invalid note query or limit')
        pattern = ('%' + query.strip().replace('!', '!!').replace('%', '!%')
                   .replace('_', '!_') + '%')
        rows = self.db.execute(
            "SELECT id, content, created_at FROM user_notes "
            "WHERE content LIKE ? ESCAPE '!' ORDER BY id DESC LIMIT ?", (pattern, limit)
        ).fetchall()
        return [{'id': int(row[0]), 'content': row[1], 'created_at': int(row[2])} for row in rows]

    def list_notes(self, limit: int = 10) -> list[dict]:
        if not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError('invalid note limit')
        rows = self.db.execute(
            'SELECT id, content, created_at FROM user_notes ORDER BY id DESC LIMIT ?', (limit,)
        ).fetchall()
        return [{'id': int(row[0]), 'content': row[1], 'created_at': int(row[2])} for row in rows]
