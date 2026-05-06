"""Base class for all Tapestry platform integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from tapestry.core.memory import MemoryStore


class BaseIntegration(ABC):
    """Abstract base that every platform adapter must implement.

    Subclasses should:
    1. Set :attr:`name` and :attr:`description` as class-level attributes.
    2. Implement :meth:`connect`, :meth:`disconnect`, and :meth:`sync`.
    3. Call ``self.memory.add_event(...)`` to persist new events.
    """

    #: Unique, machine-readable identifier (e.g. "github", "terminal")
    name: str = "base"
    #: Short human-readable description shown in the UI
    description: str = "Base integration"

    def __init__(self, memory: Optional[MemoryStore] = None, **kwargs) -> None:
        self.memory = memory or MemoryStore()
        self.connected: bool = False
        self.status: str = "disconnected"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the platform."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the connection cleanly."""

    @abstractmethod
    def sync(self) -> int:
        """Pull the latest events from the platform into memory.

        Returns the number of new entries ingested.
        """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mark_connected(self) -> None:
        self.connected = True
        self.status = "connected"

    def _mark_disconnected(self) -> None:
        self.connected = False
        self.status = "disconnected"
