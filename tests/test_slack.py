"""Tests for the Slack integration (no-network paths only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapestry.core.memory import MemoryStore
from tapestry.integrations.slack import SlackIntegration


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "slack.db")


def test_connect_without_token(store):
    s = SlackIntegration(memory=store, token="")
    s.connect()
    assert not s.connected
    assert "token" in s.status.lower()


def test_sync_without_connection_returns_zero(store):
    s = SlackIntegration(memory=store, token="")
    assert s.sync() == 0


def test_sync_channel_records_messages(store, monkeypatch):
    s = SlackIntegration(memory=store, token="xoxb-fake")

    def fake_call(method, params=None):
        if method == "auth.test":
            return {"ok": True, "user_id": "U1", "user": "alice", "team": "tapestry"}
        if method == "conversations.list":
            return {"ok": True, "channels": [{"id": "C1", "name": "general"}]}
        if method == "conversations.history":
            return {
                "ok": True,
                "messages": [
                    {"text": "hello team", "user": "U1", "ts": "1700000001.0"},
                    {"text": "ship it", "user": "U2", "ts": "1700000002.0"},
                ],
            }
        return {"ok": False}

    monkeypatch.setattr(s, "_call", fake_call)
    s.connect()
    assert s.connected

    n = s.sync()
    assert n == 2
    events = store.recent(source="slack", kind="event")
    contents = [e.content for e in events]
    assert any("hello team" in c for c in contents)
    assert any("#general" in c for c in contents)
