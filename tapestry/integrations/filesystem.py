"""Filesystem integration.

Watches a directory tree and ingests file-change events into Tapestry memory.
This lets the agent recall things like "You created report.md at 2 PM" or
"main.py was modified 3 times this session."
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from tapestry.integrations.base import BaseIntegration
from tapestry.core.memory import MemoryStore


class FilesystemIntegration(BaseIntegration):
    """Scans a watched directory and records file changes as memory events."""

    name = "filesystem"
    description = "Watches a directory and records file changes"

    def __init__(
        self,
        memory: Optional[MemoryStore] = None,
        watch_path: Optional[str] = None,
        max_depth: int = 3,
        **kwargs,
    ) -> None:
        super().__init__(memory=memory, **kwargs)
        self._watch_path = Path(watch_path or Path.home())
        self._max_depth = max_depth
        self._snapshot: dict[str, str] = {}  # path → md5

    def connect(self) -> None:
        if self._watch_path.exists():
            self._snapshot = self._take_snapshot()
            self._mark_connected()
            self.memory.add_event(
                content=f"Tapestry is now watching {self._watch_path}",
                source=self.name,
                metadata={"path": str(self._watch_path)},
            )
        else:
            self.status = f"path not found: {self._watch_path}"

    def disconnect(self) -> None:
        self._mark_disconnected()

    def sync(self) -> int:
        new_snapshot = self._take_snapshot()
        count = 0

        old_keys = set(self._snapshot)
        new_keys = set(new_snapshot)

        # Created
        for p in new_keys - old_keys:
            self.memory.add_event(
                content=f"File created: {p}",
                source=self.name,
                metadata={"path": p, "change": "created"},
            )
            count += 1

        # Deleted
        for p in old_keys - new_keys:
            self.memory.add_event(
                content=f"File deleted: {p}",
                source=self.name,
                metadata={"path": p, "change": "deleted"},
            )
            count += 1

        # Modified
        for p in old_keys & new_keys:
            if self._snapshot[p] != new_snapshot[p]:
                self.memory.add_event(
                    content=f"File modified: {p}",
                    source=self.name,
                    metadata={"path": p, "change": "modified"},
                )
                count += 1

        self._snapshot = new_snapshot
        return count

    def index_file(self, path: str) -> bool:
        """Read a text file and store its content summary in memory."""
        p = Path(path)
        if not p.is_file():
            return False
        try:
            text = p.read_text(errors="replace")
            snippet = text[:500].replace("\n", " ")
            self.memory.add_event(
                content=f"Indexed file {p.name}: {snippet}",
                source=self.name,
                metadata={"path": str(p), "size": len(text)},
            )
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------

    def _take_snapshot(self) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        try:
            for root, dirs, files in os.walk(self._watch_path):
                # Respect max_depth
                depth = Path(root).relative_to(self._watch_path).parts
                if len(depth) >= self._max_depth:
                    dirs.clear()
                    continue
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    if fname.startswith("."):
                        continue
                    full = Path(root) / fname
                    try:
                        h = _md5(full)
                        snapshot[str(full)] = h
                    except OSError:
                        pass
        except PermissionError:
            pass
        return snapshot


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
