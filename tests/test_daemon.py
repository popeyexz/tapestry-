"""Tests for IntegrationManager.run_daemon()."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from tapestry.core.integrations import IntegrationManager
from tapestry.core.memory import MemoryStore
from tapestry.integrations.base import BaseIntegration


class CountingIntegration(BaseIntegration):
    name = "counting"
    description = "Counts sync calls"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sync_calls = 0

    def connect(self):
        self._mark_connected()

    def disconnect(self):
        self._mark_disconnected()

    def sync(self) -> int:
        self.sync_calls += 1
        return 1


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "daemon.db")


def test_daemon_runs_periodically(store):
    manager = IntegrationManager(memory=store)
    integration = manager.register(CountingIntegration)
    manager.start_all()

    seen_results = []
    stop = manager.run_daemon(interval=0.05, on_sync=seen_results.append)

    # Wait long enough for at least 2 sync iterations
    time.sleep(0.2)
    manager.stop_daemon()

    assert integration.sync_calls >= 2
    assert any("counting" in r for r in seen_results)


def test_stop_daemon_is_idempotent(store):
    manager = IntegrationManager(memory=store)
    manager.register(CountingIntegration)
    manager.start_all()
    manager.run_daemon(interval=0.01)
    manager.stop_daemon()
    manager.stop_daemon()  # should not raise


def test_daemon_thread_is_daemonised(store):
    manager = IntegrationManager(memory=store)
    manager.register(CountingIntegration)
    manager.start_all()
    manager.run_daemon(interval=0.01)
    try:
        assert manager._daemon_thread is not None
        assert manager._daemon_thread.daemon is True
    finally:
        manager.stop_daemon()
