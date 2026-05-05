"""Integration manager — discovers and coordinates all connected platforms.

Each platform adapter is a subclass of BaseIntegration.  The manager keeps a
registry of active integrations and funnels their events into the unified
MemoryStore so the agent can recall them later.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional, Type

from tapestry.core.memory import MemoryStore
from tapestry.integrations.base import BaseIntegration


class IntegrationManager:
    """Manages the lifecycle of all registered platform integrations.

    Usage::

        store = MemoryStore()
        manager = IntegrationManager(store)
        manager.register(TerminalIntegration)
        manager.register(GitHubIntegration, token="ghp_…")
        manager.start_all()
    """

    def __init__(self, memory: Optional[MemoryStore] = None) -> None:
        self.memory = memory or MemoryStore()
        self._registry: Dict[str, BaseIntegration] = {}
        self._daemon_stop: Optional[threading.Event] = None
        self._daemon_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self, integration_cls: Type[BaseIntegration], **kwargs
    ) -> BaseIntegration:
        """Instantiate and register an integration.

        Extra *kwargs* are forwarded to the integration constructor so that
        credentials (tokens, paths, etc.) can be supplied at registration time.
        """
        instance = integration_cls(memory=self.memory, **kwargs)
        self._registry[instance.name] = instance
        return instance

    def get(self, name: str) -> Optional[BaseIntegration]:
        """Retrieve a registered integration by name."""
        return self._registry.get(name)

    @property
    def integrations(self) -> List[BaseIntegration]:
        return list(self._registry.values())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_all(self) -> None:
        """Connect all registered integrations."""
        for integration in self._registry.values():
            try:
                integration.connect()
            except Exception as exc:
                integration.status = f"error: {exc}"

    def stop_all(self) -> None:
        """Disconnect all registered integrations."""
        for integration in self._registry.values():
            try:
                integration.disconnect()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Status / reporting
    # ------------------------------------------------------------------

    def status_report(self) -> List[dict]:
        """Return a list of status dicts for all registered integrations."""
        return [
            {
                "name": i.name,
                "description": i.description,
                "status": i.status,
                "connected": i.connected,
            }
            for i in self._registry.values()
        ]

    def sync_all(self) -> Dict[str, int]:
        """Pull latest events from all connected integrations.

        Returns a mapping of integration name → number of new events ingested.
        """
        results: Dict[str, int] = {}
        for integration in self._registry.values():
            if integration.connected:
                try:
                    n = integration.sync()
                    results[integration.name] = n
                except Exception as exc:
                    results[integration.name] = 0
                    integration.status = f"sync error: {exc}"
        return results

    # ------------------------------------------------------------------
    # Daemon — keep memory updated continuously in the background
    # ------------------------------------------------------------------

    def run_daemon(
        self,
        interval: float = 30.0,
        on_sync: Optional[Callable[[Dict[str, int]], None]] = None,
    ) -> threading.Event:
        """Start a background thread that calls :meth:`sync_all` periodically.

        Returns a :class:`threading.Event`; set it (or call
        :meth:`stop_daemon`) to stop the loop.
        """
        if self._daemon_thread and self._daemon_thread.is_alive():
            return self._daemon_stop  # already running

        stop = threading.Event()
        self._daemon_stop = stop

        def _loop() -> None:
            while not stop.is_set():
                results = self.sync_all()
                if on_sync:
                    try:
                        on_sync(results)
                    except Exception:
                        pass
                stop.wait(interval)

        thread = threading.Thread(target=_loop, daemon=True, name="tapestry-daemon")
        thread.start()
        self._daemon_thread = thread
        return stop

    def stop_daemon(self) -> None:
        """Signal the daemon loop (if any) to stop and wait for it."""
        if self._daemon_stop:
            self._daemon_stop.set()
        if self._daemon_thread:
            self._daemon_thread.join(timeout=2.0)
        self._daemon_stop = None
        self._daemon_thread = None
