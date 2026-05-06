"""Terminal / shell integration.

Captures commands run in the current shell session (via shell history) and
stores them as Tapestry memory events so the agent can recall what you ran.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from tapestry.integrations.base import BaseIntegration
from tapestry.core.memory import MemoryStore


class TerminalIntegration(BaseIntegration):
    """Reads shell history (bash/zsh) and ingests recent commands."""

    name = "terminal"
    description = "Captures shell commands from your terminal history"

    def __init__(
        self,
        memory: Optional[MemoryStore] = None,
        history_file: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(memory=memory, **kwargs)
        self._history_file = Path(
            history_file
            or os.environ.get("HISTFILE", "")
            or Path.home() / ".bash_history"
        )
        self._last_line: int = 0

    def connect(self) -> None:
        if self._history_file.exists():
            # Remember how many lines we've already seen
            self._last_line = self._count_lines()
            self._mark_connected()
        else:
            self.status = f"history file not found: {self._history_file}"

    def disconnect(self) -> None:
        self._mark_disconnected()

    def sync(self) -> int:
        if not self._history_file.exists():
            return 0
        current_count = self._count_lines()
        if current_count <= self._last_line:
            return 0
        new_lines = self._read_lines(self._last_line, current_count)
        self._last_line = current_count
        count = 0
        for cmd in new_lines:
            cmd = cmd.strip()
            if cmd and not cmd.startswith("#"):
                self.memory.add_event(
                    content=f"$ {cmd}",
                    source=self.name,
                    metadata={"command": cmd},
                )
                count += 1
        return count

    def run_command(self, command: str, capture: bool = True) -> str:
        """Execute a shell command and store both the command and output."""
        self.memory.add_event(
            content=f"$ {command}",
            source=self.name,
            metadata={"command": command, "type": "run"},
        )
        if capture:
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = result.stdout or result.stderr or "(no output)"
                output = output[:2000]  # cap storage size
                self.memory.add_event(
                    content=output,
                    source=self.name,
                    metadata={"command": command, "type": "output",
                               "returncode": result.returncode},
                )
                return output
            except subprocess.TimeoutExpired:
                return "(command timed out)"
        return ""

    # ------------------------------------------------------------------

    def _count_lines(self) -> int:
        try:
            with open(self._history_file, "rb") as f:
                return sum(1 for _ in f)
        except OSError:
            return 0

    def _read_lines(self, start: int, end: int) -> list[str]:
        try:
            with open(self._history_file, errors="replace") as f:
                lines = f.readlines()
            return lines[start:end]
        except OSError:
            return []
