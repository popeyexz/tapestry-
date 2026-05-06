"""Tests for platform integrations."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapestry.core.memory import MemoryStore
from tapestry.core.integrations import IntegrationManager
from tapestry.integrations.base import BaseIntegration
from tapestry.integrations.terminal import TerminalIntegration
from tapestry.integrations.filesystem import FilesystemIntegration
from tapestry.integrations.github import GitHubIntegration


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "int_test.db")


# ---------------------------------------------------------------------------
# BaseIntegration subclassing
# ---------------------------------------------------------------------------

class FakeIntegration(BaseIntegration):
    name = "fake"
    description = "Fake test integration"

    def connect(self):
        self._mark_connected()

    def disconnect(self):
        self._mark_disconnected()

    def sync(self) -> int:
        self.memory.add_event("fake event", source=self.name)
        return 1


class TestBaseIntegration:
    def test_initial_state(self, store: MemoryStore):
        i = FakeIntegration(memory=store)
        assert not i.connected
        assert i.status == "disconnected"

    def test_connect(self, store: MemoryStore):
        i = FakeIntegration(memory=store)
        i.connect()
        assert i.connected
        assert i.status == "connected"

    def test_disconnect(self, store: MemoryStore):
        i = FakeIntegration(memory=store)
        i.connect()
        i.disconnect()
        assert not i.connected
        assert i.status == "disconnected"

    def test_sync_writes_memory(self, store: MemoryStore):
        i = FakeIntegration(memory=store)
        i.connect()
        n = i.sync()
        assert n == 1
        events = store.recent(source="fake", kind="event")
        assert len(events) == 1
        assert events[0].content == "fake event"


# ---------------------------------------------------------------------------
# IntegrationManager
# ---------------------------------------------------------------------------

class TestIntegrationManager:
    def test_register(self, store: MemoryStore):
        manager = IntegrationManager(memory=store)
        i = manager.register(FakeIntegration)
        assert isinstance(i, FakeIntegration)
        assert manager.get("fake") is i

    def test_start_all(self, store: MemoryStore):
        manager = IntegrationManager(memory=store)
        manager.register(FakeIntegration)
        manager.start_all()
        assert manager.get("fake").connected

    def test_stop_all(self, store: MemoryStore):
        manager = IntegrationManager(memory=store)
        manager.register(FakeIntegration)
        manager.start_all()
        manager.stop_all()
        assert not manager.get("fake").connected

    def test_sync_all(self, store: MemoryStore):
        manager = IntegrationManager(memory=store)
        manager.register(FakeIntegration)
        manager.start_all()
        results = manager.sync_all()
        assert results["fake"] == 1

    def test_status_report(self, store: MemoryStore):
        manager = IntegrationManager(memory=store)
        manager.register(FakeIntegration)
        manager.start_all()
        report = manager.status_report()
        assert len(report) == 1
        assert report[0]["name"] == "fake"
        assert report[0]["connected"] is True

    def test_multiple_integrations(self, store: MemoryStore):
        class FakeTwo(FakeIntegration):
            name = "fake2"

        manager = IntegrationManager(memory=store)
        manager.register(FakeIntegration)
        manager.register(FakeTwo)
        manager.start_all()
        assert len(manager.integrations) == 2


# ---------------------------------------------------------------------------
# TerminalIntegration
# ---------------------------------------------------------------------------

class TestTerminalIntegration:
    def test_connect_with_existing_history(self, store: MemoryStore, tmp_path: Path):
        hist = tmp_path / ".bash_history"
        hist.write_text("ls\necho hello\n")
        t = TerminalIntegration(memory=store, history_file=str(hist))
        t.connect()
        assert t.connected

    def test_connect_missing_history(self, store: MemoryStore, tmp_path: Path):
        t = TerminalIntegration(
            memory=store, history_file=str(tmp_path / "nonexistent")
        )
        t.connect()
        assert not t.connected

    def test_sync_detects_new_commands(self, store: MemoryStore, tmp_path: Path):
        hist = tmp_path / ".bash_history"
        hist.write_text("ls\n")
        t = TerminalIntegration(memory=store, history_file=str(hist))
        t.connect()
        # Add new commands
        with open(hist, "a") as f:
            f.write("git status\ngit push\n")
        n = t.sync()
        assert n == 2
        events = store.recent(source="terminal", kind="event")
        cmds = [e.content for e in events]
        assert any("git status" in c for c in cmds)

    def test_run_command(self, store: MemoryStore, tmp_path: Path):
        hist = tmp_path / ".bash_history"
        hist.write_text("")
        t = TerminalIntegration(memory=store, history_file=str(hist))
        t.connect()
        output = t.run_command("echo tapestry")
        assert "tapestry" in output
        # Should have stored 2 events: the command + the output
        events = store.recent(source="terminal", kind="event")
        assert len(events) >= 2


# ---------------------------------------------------------------------------
# FilesystemIntegration
# ---------------------------------------------------------------------------

class TestFilesystemIntegration:
    def test_connect(self, store: MemoryStore, tmp_path: Path):
        f = FilesystemIntegration(memory=store, watch_path=str(tmp_path))
        f.connect()
        assert f.connected

    def test_connect_missing_path(self, store: MemoryStore, tmp_path: Path):
        f = FilesystemIntegration(
            memory=store, watch_path=str(tmp_path / "nonexistent")
        )
        f.connect()
        assert not f.connected

    def test_sync_detects_created_file(self, store: MemoryStore, tmp_path: Path):
        f = FilesystemIntegration(memory=store, watch_path=str(tmp_path))
        f.connect()
        (tmp_path / "newfile.txt").write_text("hello")
        n = f.sync()
        assert n >= 1
        events = store.recent(source="filesystem", kind="event")
        assert any("created" in e.content.lower() for e in events)

    def test_sync_detects_modified_file(self, store: MemoryStore, tmp_path: Path):
        existing = tmp_path / "existing.txt"
        existing.write_text("original")
        f = FilesystemIntegration(memory=store, watch_path=str(tmp_path))
        f.connect()
        existing.write_text("modified content")
        n = f.sync()
        assert n >= 1
        events = store.recent(source="filesystem", kind="event")
        assert any("modified" in e.content.lower() for e in events)

    def test_index_file(self, store: MemoryStore, tmp_path: Path):
        target = tmp_path / "notes.txt"
        target.write_text("Important note about Tapestry")
        f = FilesystemIntegration(memory=store, watch_path=str(tmp_path))
        f.connect()
        result = f.index_file(str(target))
        assert result is True
        events = store.recent(source="filesystem", kind="event")
        assert any("Indexed file" in e.content for e in events)


# ---------------------------------------------------------------------------
# GitHubIntegration — no-token path
# ---------------------------------------------------------------------------

class TestGitHubIntegrationNoToken:
    def test_connect_without_token(self, store: MemoryStore):
        g = GitHubIntegration(memory=store, token="")
        g.connect()
        assert not g.connected
        assert "token" in g.status.lower()
