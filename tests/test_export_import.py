"""Tests for memory export/import — the cross-device sync mechanism."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tapestry.core.memory import MemoryStore


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "export.db")


def test_export_entries_returns_dicts(store):
    store.add_message("hello", source="chat")
    entries = store.export_entries()
    assert len(entries) == 1
    assert entries[0]["content"] == "hello"
    assert isinstance(entries[0]["metadata"], dict)


def test_export_to_file_writes_json(store, tmp_path: Path):
    store.add_message("hello", source="chat", metadata={"k": "v"})
    out = tmp_path / "memory.json"
    n = store.export_to_file(out)
    assert n == 1
    data = json.loads(out.read_text())
    assert data[0]["content"] == "hello"
    assert data[0]["metadata"] == {"k": "v"}


def test_import_entries_inserts_and_dedupes(tmp_path: Path):
    src = MemoryStore(db_path=tmp_path / "src.db")
    src.add_message("a", source="chat")
    src.add_message("b", source="chat")

    dst = MemoryStore(db_path=tmp_path / "dst.db")
    payload = src.export_entries()
    assert dst.import_entries(payload) == 2
    # Re-importing the same payload is idempotent
    assert dst.import_entries(payload) == 0
    assert dst.stats()["total"] == 2


def test_import_from_file(tmp_path: Path):
    src = MemoryStore(db_path=tmp_path / "src.db")
    src.add_event("pushed", source="github")
    out = tmp_path / "exp.json"
    src.export_to_file(out)

    dst = MemoryStore(db_path=tmp_path / "dst.db")
    n = dst.import_from_file(out)
    assert n == 1
    entries = dst.recent(source="github")
    assert entries[0].content == "pushed"


def test_import_rejects_non_list(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"not": "a list"}))
    store = MemoryStore(db_path=tmp_path / "store.db")
    with pytest.raises(ValueError):
        store.import_from_file(bad)
