"""Tapestry CLI — command-line interface.

Commands:
  tapestry chat         Interactive conversation with the agent
  tapestry ui           Full TUI (platforms + chat panels)
  tapestry memory list  Show recent memories
  tapestry memory search <query>
  tapestry memory stats
  tapestry memory clear [--source SOURCE]
  tapestry connect      Register and start a platform integration
  tapestry sync         Pull latest events from all connected platforms
  tapestry story        Print your cross-platform narrative
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich import box

from tapestry.core.agent import Agent, _fmt_ts, _source_icon
from tapestry.core.memory import MemoryStore
from tapestry.core.integrations import IntegrationManager

console = Console()

# Shared state injected via Click context
pass_agent = click.make_pass_decorator(Agent, ensure=True)


def _make_agent() -> Agent:
    return Agent()


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="tapestry")
@click.pass_context
def main(ctx: click.Context) -> None:
    """🧵 Tapestry — your unified AI memory across every platform."""
    ctx.ensure_object(dict)
    ctx.obj["agent"] = _make_agent()


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------

@main.command()
@click.option("--source", default="chat", show_default=True,
              help="Memory source label for this session.")
@click.pass_context
def chat(ctx: click.Context, source: str) -> None:
    """Start an interactive conversation with the Tapestry agent."""
    agent: Agent = ctx.obj["agent"]

    console.rule("[bold magenta]🧵 Tapestry Chat[/bold magenta]")
    console.print(
        "[dim]Your unified AI memory. Type 'help' for commands, Ctrl+C to exit.[/dim]\n"
    )
    console.print(f"[bold magenta]Tapestry:[/bold magenta] {agent.greet()}\n")

    while True:
        try:
            user_input = click.prompt(
                click.style("You", fg="cyan", bold=True), prompt_suffix=" > "
            ).strip()
        except (click.Abort, EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye — your memories are saved.[/dim]")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "bye"}:
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() == "help":
            console.print(
                "[bold]Commands:[/bold]\n"
                "  story            — your cross-platform narrative\n"
                "  stats            — memory statistics\n"
                "  recall <term>    — search memories\n"
                "  exit / quit      — exit"
            )
            continue

        reply = agent.chat(user_input, source=source)
        console.print(f"\n[bold magenta]Tapestry:[/bold magenta] {reply}\n")


# ---------------------------------------------------------------------------
# ui
# ---------------------------------------------------------------------------

@main.command()
@click.option("--github-token", envvar="TAPESTRY_GITHUB_TOKEN",
              help="GitHub Personal Access Token.")
@click.option("--watch", default=None, metavar="PATH",
              help="Directory to watch with the filesystem integration.")
@click.pass_context
def ui(ctx: click.Context, github_token: Optional[str], watch: Optional[str]) -> None:
    """Launch the full Tapestry TUI with platform panels."""
    from tapestry.ui.app import run_interactive_ui
    from tapestry.integrations.terminal import TerminalIntegration
    from tapestry.integrations.filesystem import FilesystemIntegration
    from tapestry.integrations.github import GitHubIntegration

    agent: Agent = ctx.obj["agent"]
    manager = IntegrationManager(memory=agent.memory)

    manager.register(TerminalIntegration)
    if watch:
        manager.register(FilesystemIntegration, watch_path=watch)
    if github_token:
        manager.register(GitHubIntegration, token=github_token)

    manager.start_all()
    run_interactive_ui(agent=agent, manager=manager)
    manager.stop_all()


# ---------------------------------------------------------------------------
# story
# ---------------------------------------------------------------------------

@main.command()
@click.option("--limit", default=30, show_default=True,
              help="Number of memories to include in the story.")
@click.pass_context
def story(ctx: click.Context, limit: int) -> None:
    """Print your cross-platform story / narrative."""
    agent: Agent = ctx.obj["agent"]
    console.print(agent.story(limit=limit))


# ---------------------------------------------------------------------------
# memory group
# ---------------------------------------------------------------------------

@main.group()
def memory() -> None:
    """Manage Tapestry's unified memory store."""


@memory.command("list")
@click.option("--source", default=None, help="Filter by platform source.")
@click.option("--kind", default=None, help="Filter by kind (message/fact/event).")
@click.option("--limit", default=20, show_default=True)
@click.pass_context
def memory_list(
    ctx: click.Context,
    source: Optional[str],
    kind: Optional[str],
    limit: int,
) -> None:
    """List recent memory entries."""
    store: MemoryStore = ctx.obj["agent"].memory
    entries = store.recent(limit=limit, source=source, kind=kind)
    _print_entries(entries)


@memory.command("search")
@click.argument("query")
@click.option("--source", default=None)
@click.option("--limit", default=20, show_default=True)
@click.pass_context
def memory_search(
    ctx: click.Context,
    query: str,
    source: Optional[str],
    limit: int,
) -> None:
    """Search memory entries by content."""
    store: MemoryStore = ctx.obj["agent"].memory
    entries = store.search(query, source=source, limit=limit)
    if not entries:
        console.print(f"[yellow]No memories found matching '{query}'.[/yellow]")
        return
    console.print(f"[bold]Found {len(entries)} memories for '{query}':[/bold]\n")
    _print_entries(entries)


@memory.command("stats")
@click.pass_context
def memory_stats(ctx: click.Context) -> None:
    """Show memory statistics."""
    store: MemoryStore = ctx.obj["agent"].memory
    stats = store.stats()
    console.print(f"[bold]Total memories:[/bold] {stats['total']}\n")
    if stats["by_source"]:
        t = Table("Platform", "Count", box=box.SIMPLE)
        for src, n in stats["by_source"].items():
            t.add_row(f"{_source_icon(src)} {src}", str(n))
        console.print(t)
    if stats["by_kind"]:
        t = Table("Kind", "Count", box=box.SIMPLE)
        for kind, n in stats["by_kind"].items():
            t.add_row(kind, str(n))
        console.print(t)


@memory.command("add-fact")
@click.argument("fact")
@click.option("--source", default="tapestry", show_default=True)
@click.pass_context
def memory_add_fact(ctx: click.Context, fact: str, source: str) -> None:
    """Store a durable fact that the agent will always remember."""
    store: MemoryStore = ctx.obj["agent"].memory
    entry = store.add_fact(fact, source=source)
    console.print(f"[green]✓ Fact stored:[/green] {entry.content}")


@memory.command("clear")
@click.option("--source", default=None, help="Only clear memories from this platform.")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def memory_clear(ctx: click.Context, source: Optional[str], yes: bool) -> None:
    """Delete memory entries."""
    store: MemoryStore = ctx.obj["agent"].memory
    target = f"from '{source}'" if source else "ALL"
    if not yes:
        click.confirm(f"Delete memories {target}?", abort=True)
    n = store.clear(source=source)
    console.print(f"[green]Deleted {n} memory entries.[/green]")


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

@main.command()
@click.argument("platform", type=click.Choice(["terminal", "filesystem", "github"]))
@click.option("--token", default=None, help="API token (for github).")
@click.option("--path", "watch_path", default=None, help="Path (for filesystem).")
@click.pass_context
def connect(
    ctx: click.Context,
    platform: str,
    token: Optional[str],
    watch_path: Optional[str],
) -> None:
    """Connect a platform integration and sync initial events."""
    from tapestry.integrations.terminal import TerminalIntegration
    from tapestry.integrations.filesystem import FilesystemIntegration
    from tapestry.integrations.github import GitHubIntegration

    agent: Agent = ctx.obj["agent"]
    manager = IntegrationManager(memory=agent.memory)

    cls_map = {
        "terminal": (TerminalIntegration, {}),
        "filesystem": (FilesystemIntegration, {"watch_path": watch_path}),
        "github": (GitHubIntegration, {"token": token}),
    }
    cls, kwargs = cls_map[platform]
    integration = manager.register(cls, **{k: v for k, v in kwargs.items() if v})
    integration.connect()
    console.print(
        f"[{'green' if integration.connected else 'red'}]"
        f"{_source_icon(platform)} {platform}: {integration.status}"
        "[/]"
    )
    if integration.connected:
        n = integration.sync()
        console.print(f"[dim]Synced {n} initial events.[/dim]")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

@main.command()
@click.option("--github-token", envvar="TAPESTRY_GITHUB_TOKEN")
@click.pass_context
def sync(ctx: click.Context, github_token: Optional[str]) -> None:
    """Pull latest events from all detected integrations."""
    from tapestry.integrations.terminal import TerminalIntegration
    from tapestry.integrations.filesystem import FilesystemIntegration
    from tapestry.integrations.github import GitHubIntegration

    agent: Agent = ctx.obj["agent"]
    manager = IntegrationManager(memory=agent.memory)
    manager.register(TerminalIntegration)
    if github_token:
        manager.register(GitHubIntegration, token=github_token)
    manager.start_all()
    results = manager.sync_all()
    total = sum(results.values())
    console.print(f"[green]Synced {total} new events across {len(results)} platform(s).[/green]")
    for name, n in results.items():
        console.print(f"  {_source_icon(name)} {name}: {n} new")
    manager.stop_all()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_entries(entries) -> None:
    if not entries:
        console.print("[yellow]No entries found.[/yellow]")
        return
    t = Table("Time", "Source", "Kind", "Content", box=box.SIMPLE, expand=True)
    for e in entries:
        t.add_row(
            _fmt_ts(e.timestamp),
            f"{_source_icon(e.source)} {e.source}",
            e.kind,
            e.content[:80],
        )
    console.print(t)
