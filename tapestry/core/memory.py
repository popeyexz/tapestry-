"""Unified persistent memory store for Tapestry.

Every interaction — from every connected platform and terminal — is written
into a single SQLite database so the AI agent can recall your full history
across all apps and sessions.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List, Optional

def _default_db_path() -> Path:
    return Path.home() / ".tapestry" / "memory.db"


DEFAULT_DB_PATH = _default_db_path()  # kept for backwards compatibility


@dataclass
class MemoryEntry:
    """A single unit of memory: a conversation turn, fact, or platform event."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = "tapestry"       # e.g. "chat", "github", "terminal", "filesystem"
    kind: str = "message"          # "message" | "fact" | "event" | "summary"
    role: str = "user"             # "user" | "assistant" | "system"
    content: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metadata"] = json.dumps(d["metadata"])
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "MemoryEntry":
        d = dict(row)
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return cls(**d)


class MemoryStore:
    """SQLite-backed store for all Tapestry memory entries.

    Usage::

        store = MemoryStore()
        store.add(MemoryEntry(source="github", kind="event",
                               role="system", content="Opened PR #42"))
        entries = store.search("PR #42")
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    id        TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    source    TEXT NOT NULL,
                    kind      TEXT NOT NULL,
                    role      TEXT NOT NULL,
                    content   TEXT NOT NULL,
                    metadata  TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_source ON memory(source)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kind ON memory(kind)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON memory(timestamp)"
            )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, entry: MemoryEntry) -> MemoryEntry:
        """Persist a memory entry and return it."""
        with self._connect() as conn:
            d = entry.to_dict()
            conn.execute(
                """
                INSERT OR REPLACE INTO memory
                    (id, timestamp, source, kind, role, content, metadata)
                VALUES
                    (:id, :timestamp, :source, :kind, :role, :content, :metadata)
                """,
                d,
            )
        return entry

    def add_message(
        self,
        content: str,
        role: str = "user",
        source: str = "chat",
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Convenience helper to store a conversation message."""
        entry = MemoryEntry(
            source=source,
            kind="message",
            role=role,
            content=content,
            metadata=metadata or {},
        )
        return self.add(entry)

    def add_fact(
        self,
        content: str,
        source: str = "tapestry",
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Store a durable fact (e.g. 'User prefers dark mode')."""
        entry = MemoryEntry(
            source=source,
            kind="fact",
            role="system",
            content=content,
            metadata=metadata or {},
        )
        return self.add(entry)

    def add_event(
        self,
        content: str,
        source: str,
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Store a platform event (e.g. a GitHub PR, a terminal command)."""
        entry = MemoryEntry(
            source=source,
            kind="event",
            role="system",
            content=content,
            metadata=metadata or {},
        )
        return self.add(entry)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        source: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryEntry]:
        """Full-text search over content (case-insensitive substring match)."""
        clauses = ["content LIKE :query"]
        params: dict = {"query": f"%{query}%", "limit": limit}
        if source:
            clauses.append("source = :source")
            params["source"] = source
        if kind:
            clauses.append("kind = :kind")
            params["kind"] = kind
        where = " AND ".join(clauses)
        sql = f"""
            SELECT * FROM memory
            WHERE {where}
            ORDER BY timestamp DESC
            LIMIT :limit
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [MemoryEntry.from_row(r) for r in rows]

    def recent(
        self,
        limit: int = 50,
        source: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """Return the most recent memory entries."""
        clauses = []
        params: dict = {"limit": limit}
        if source:
            clauses.append("source = :source")
            params["source"] = source
        if kind:
            clauses.append("kind = :kind")
            params["kind"] = kind
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT * FROM memory
            {where}
            ORDER BY timestamp DESC
            LIMIT :limit
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [MemoryEntry.from_row(r) for r in rows]

    def conversation_history(
        self,
        limit: int = 40,
        source: str = "chat",
    ) -> List[MemoryEntry]:
        """Return recent conversation messages for context injection."""
        entries = self.recent(limit=limit, source=source, kind="message")
        return list(reversed(entries))  # chronological order

    def stats(self) -> dict:
        """Return summary statistics about stored memory."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
            by_source = conn.execute(
                "SELECT source, COUNT(*) AS n FROM memory GROUP BY source ORDER BY n DESC"
            ).fetchall()
            by_kind = conn.execute(
                "SELECT kind, COUNT(*) AS n FROM memory GROUP BY kind ORDER BY n DESC"
            ).fetchall()
        return {
            "total": total,
            "by_source": {r["source"]: r["n"] for r in by_source},
            "by_kind": {r["kind"]: r["n"] for r in by_kind},
        }

    def clear(self, source: Optional[str] = None) -> int:
        """Delete entries. Returns number of rows deleted."""
        if source:
            sql = "DELETE FROM memory WHERE source = ?"
            params: tuple = (source,)
        else:
            sql = "DELETE FROM memory"
            params = ()
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount

    # ------------------------------------------------------------------
    # Portability — export/import the whole memory so it follows you
    # across machines and apps.
    # ------------------------------------------------------------------

    def export_entries(self) -> List[dict]:
        """Return every memory entry as a list of plain dicts (JSON-safe)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory ORDER BY timestamp ASC"
            ).fetchall()
        out: List[dict] = []
        for row in rows:
            d = dict(row)
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            out.append(d)
        return out

    def export_to_file(self, path: Path) -> int:
        """Write all memories to a JSON file. Returns number of entries."""
        entries = self.export_entries()
        Path(path).write_text(json.dumps(entries, indent=2))
        return len(entries)

    def import_entries(self, entries: List[dict]) -> int:
        """Insert entries from another store, skipping duplicates by id."""
        added = 0
        with self._connect() as conn:
            for d in entries:
                meta = d.get("metadata", {})
                if isinstance(meta, dict):
                    meta = json.dumps(meta)
                row = {
                    "id": d.get("id") or str(uuid.uuid4()),
                    "timestamp": d.get("timestamp")
                    or datetime.now(timezone.utc).isoformat(),
                    "source": d.get("source", "tapestry"),
                    "kind": d.get("kind", "message"),
                    "role": d.get("role", "system"),
                    "content": d.get("content", ""),
                    "metadata": meta,
                }
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO memory
                        (id, timestamp, source, kind, role, content, metadata)
                    VALUES
                        (:id, :timestamp, :source, :kind, :role, :content, :metadata)
                    """,
                    row,
                )
                added += cur.rowcount
        return added

    def import_from_file(self, path: Path) -> int:
        """Read a JSON export file and merge into this store."""
        data = json.loads(Path(path).read_text())
        if not isinstance(data, list):
            raise ValueError("import file must contain a JSON array")
        return self.import_entries(data)
