"""Rich-based Terminal UI for Tapestry.

Provides an interactive desktop-like experience inside the terminal:
- Left panel: connected platforms + status
- Right panel: conversation chat with the Tapestry agent
- Bottom: command input

Run with: tapestry ui
"""

from __future__ import annotations

import sys
import textwrap
from datetime import datetime, timezone
from typing import List, Optional

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich import box

from tapestry.core.agent import Agent, _fmt_ts, _source_icon
from tapestry.core.memory import MemoryEntry, MemoryStore
from tapestry.core.integrations import IntegrationManager

console = Console()


# ---------------------------------------------------------------------------
# Utility renderers
# ---------------------------------------------------------------------------

def render_platforms(manager: Optional[IntegrationManager]) -> Panel:
    """Render the platform status panel."""
    table = Table(box=box.SIMPLE, show_header=True, expand=True)
    table.add_column("Platform", style="bold cyan", min_width=12)
    table.add_column("Status", min_width=12)

    if manager:
        for info in manager.status_report():
            icon = _source_icon(info["name"])
            status = info["status"]
            color = "green" if info["connected"] else "red"
            table.add_row(
                f"{icon} {info['name']}",
                Text(status, style=color),
            )
    else:
        table.add_row("💬 chat", Text("active", style="green"))

    return Panel(table, title="[bold]🔌 Connected Platforms[/bold]", border_style="blue")


def render_chat(messages: List[dict]) -> Panel:
    """Render the conversation panel."""
    lines: List[str] = []
    for msg in messages[-20:]:  # show last 20 turns
        role = msg["role"]
        content = msg["content"]
        ts = msg.get("ts", "")
        if role == "user":
            lines.append(f"[bold cyan]You[/bold cyan] [dim]{ts}[/dim]")
            lines.append(f"  {content}\n")
        else:
            lines.append(f"[bold magenta]🧵 Tapestry[/bold magenta] [dim]{ts}[/dim]")
            for line in content.split("\n"):
                lines.append(f"  {line}")
            lines.append("")
    body = "\n".join(lines) if lines else "[dim]No messages yet. Start chatting![/dim]"
    return Panel(body, title="[bold]💬 Conversation[/bold]", border_style="magenta")


def render_memory_bar(store: MemoryStore) -> Panel:
    """Render a compact memory statistics bar."""
    stats = store.stats()
    total = stats.get("total", 0)
    by_src = stats.get("by_source", {})
    parts = [f"[bold]{total}[/bold] memories"]
    for src, n in list(by_src.items())[:4]:
        parts.append(f"{_source_icon(src)} {src}:{n}")
    return Panel(
        "  ".join(parts),
        title="[bold]🧠 Memory[/bold]",
        border_style="yellow",
        height=3,
    )


# ---------------------------------------------------------------------------
# Main interactive UI
# ---------------------------------------------------------------------------

def run_interactive_ui(
    agent: Agent,
    manager: Optional[IntegrationManager] = None,
) -> None:
    """Run the full Tapestry TUI session."""
    messages: List[dict] = []

    def _ts() -> str:
        return datetime.now(timezone.utc).strftime("%H:%M")

    def _add(role: str, content: str) -> None:
        messages.append({"role": role, "content": content, "ts": _ts()})

    # Greet
    greeting = agent.greet()
    _add("assistant", greeting)

    console.clear()
    console.rule("[bold magenta]🧵 Tapestry[/bold magenta]")
    console.print(
        "[dim]Your unified AI memory across every platform. "
        "Type your message, or 'help' for commands. Ctrl+C to exit.[/dim]\n"
    )

    while True:
        # Redraw
        console.print(render_platforms(manager))
        console.print(render_chat(messages))
        console.print(render_memory_bar(agent.memory))

        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye — your memories are saved.[/dim]")
            break

        if not user_input:
            continue

        # Built-in UI commands
        if user_input.lower() in {"exit", "quit", "bye"}:
            console.print("[dim]Goodbye — your memories are saved.[/dim]")
            break

        if user_input.lower() == "help":
            _add("user", user_input)
            _add(
                "assistant",
                textwrap.dedent(
                    """
                    Available commands:
                      help          — show this message
                      story         — tell me your cross-platform story
                      stats         — memory statistics
                      recall <term> — search memories for <term>
                      exit / quit   — exit Tapestry
                    Or just chat naturally — I remember everything!
                    """
                ).strip(),
            )
            console.clear()
            continue

        if user_input.lower() == "sync" and manager:
            _add("user", user_input)
            results = manager.sync_all()
            lines = [f"Synced {sum(results.values())} new events:"]
            for name, n in results.items():
                lines.append(f"  {_source_icon(name)} {name}: {n} new")
            _add("assistant", "\n".join(lines))
            console.clear()
            continue

        # Normal chat turn
        _add("user", user_input)
        console.print("[dim]Thinking…[/dim]")
        reply = agent.chat(user_input)
        _add("assistant", reply)
        console.clear()
