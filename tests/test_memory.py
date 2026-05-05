"""Tests for tapestry.core.memory."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tapestry.core.memory import MemoryEntry, MemoryStore


@pytest.fixture()
def tmp_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "test_memory.db")


# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------

class TestMemoryEntry:
    def test_defaults(self):
        e = MemoryEntry()
        assert e.id
        assert e.timestamp
        assert e.source == "tapestry"
        assert e.kind == "message"
        assert e.role == "user"
        assert e.content == ""
        assert e.metadata == {}

    def test_to_dict_serialises_metadata(self):
        e = MemoryEntry(metadata={"key": "value"})
        d = e.to_dict()
        assert d["metadata"] == '{"key": "value"}'

    def test_from_row_round_trip(self):
        import sqlite3, json

        e = MemoryEntry(content="hello", metadata={"x": 1})
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE memory "
            "(id TEXT, timestamp TEXT, source TEXT, kind TEXT, "
            " role TEXT, content TEXT, metadata TEXT)"
        )
        d = e.to_dict()
        db.execute(
            "INSERT INTO memory VALUES (?,?,?,?,?,?,?)",
            (d["id"], d["timestamp"], d["source"], d["kind"],
             d["role"], d["content"], d["metadata"]),
        )
        db.commit()
        row = db.execute("SELECT * FROM memory").fetchone()
        e2 = MemoryEntry.from_row(row)
        assert e2.id == e.id
        assert e2.content == "hello"
        assert e2.metadata == {"x": 1}


# ---------------------------------------------------------------------------
# MemoryStore — write
# ---------------------------------------------------------------------------

class TestMemoryStoreWrite:
    def test_add_returns_entry(self, tmp_store: MemoryStore):
        e = MemoryEntry(content="Test entry")
        returned = tmp_store.add(e)
        assert returned.id == e.id

    def test_add_message(self, tmp_store: MemoryStore):
        e = tmp_store.add_message("Hello world", role="user", source="chat")
        assert e.kind == "message"
        assert e.role == "user"
        assert e.source == "chat"
        assert e.content == "Hello world"

    def test_add_fact(self, tmp_store: MemoryStore):
        e = tmp_store.add_fact("User prefers dark mode", source="tapestry")
        assert e.kind == "fact"
        assert e.role == "system"

    def test_add_event(self, tmp_store: MemoryStore):
        e = tmp_store.add_event("Pushed to main", source="github")
        assert e.kind == "event"
        assert e.source == "github"

    def test_add_preserves_metadata(self, tmp_store: MemoryStore):
        e = tmp_store.add_message("hi", metadata={"session": "abc"})
        results = tmp_store.search("hi")
        assert results[0].metadata == {"session": "abc"}


# ---------------------------------------------------------------------------
# MemoryStore — read
# ---------------------------------------------------------------------------

class TestMemoryStoreRead:
    def _populate(self, store: MemoryStore) -> None:
        store.add_message("hello from chat", source="chat")
        store.add_message("hi from terminal", source="terminal")
        store.add_event("Pushed code", source="github")
        store.add_fact("User likes Python", source="tapestry")

    def test_search_finds_matching(self, tmp_store: MemoryStore):
        self._populate(tmp_store)
        results = tmp_store.search("hello")
        assert len(results) == 1
        assert "hello" in results[0].content

    def test_search_no_match(self, tmp_store: MemoryStore):
        self._populate(tmp_store)
        assert tmp_store.search("xyz_nonexistent") == []

    def test_search_filter_source(self, tmp_store: MemoryStore):
        self._populate(tmp_store)
        results = tmp_store.search("hi", source="terminal")
        assert all(r.source == "terminal" for r in results)

    def test_search_filter_kind(self, tmp_store: MemoryStore):
        self._populate(tmp_store)
        results = tmp_store.search("", kind="fact")
        # The LIKE %% query matches all rows, filtered to kind=fact
        assert all(r.kind == "fact" for r in results)

    def test_recent_all(self, tmp_store: MemoryStore):
        self._populate(tmp_store)
        results = tmp_store.recent(limit=10)
        assert len(results) == 4

    def test_recent_filter_source(self, tmp_store: MemoryStore):
        self._populate(tmp_store)
        results = tmp_store.recent(limit=10, source="github")
        assert all(r.source == "github" for r in results)

    def test_recent_limit_respected(self, tmp_store: MemoryStore):
        for i in range(10):
            tmp_store.add_message(f"msg {i}")
        results = tmp_store.recent(limit=3)
        assert len(results) == 3

    def test_conversation_history_chronological(self, tmp_store: MemoryStore):
        tmp_store.add_message("first", source="chat")
        tmp_store.add_message("second", source="chat")
        tmp_store.add_message("third", source="chat")
        history = tmp_store.conversation_history(limit=10, source="chat")
        contents = [e.content for e in history]
        assert contents == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# MemoryStore — stats & clear
# ---------------------------------------------------------------------------

class TestMemoryStoreStats:
    def test_stats_empty(self, tmp_store: MemoryStore):
        stats = tmp_store.stats()
        assert stats["total"] == 0
        assert stats["by_source"] == {}
        assert stats["by_kind"] == {}

    def test_stats_after_inserts(self, tmp_store: MemoryStore):
        tmp_store.add_message("a", source="chat")
        tmp_store.add_message("b", source="chat")
        tmp_store.add_event("c", source="github")
        stats = tmp_store.stats()
        assert stats["total"] == 3
        assert stats["by_source"]["chat"] == 2
        assert stats["by_source"]["github"] == 1

    def test_clear_all(self, tmp_store: MemoryStore):
        tmp_store.add_message("a")
        tmp_store.add_message("b")
        n = tmp_store.clear()
        assert n == 2
        assert tmp_store.stats()["total"] == 0

    def test_clear_by_source(self, tmp_store: MemoryStore):
        tmp_store.add_message("a", source="chat")
        tmp_store.add_event("b", source="github")
        n = tmp_store.clear(source="chat")
        assert n == 1
        remaining = tmp_store.recent(limit=10)
        assert all(r.source == "github" for r in remaining)
