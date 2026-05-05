# 🧵 Tapestry

**Your unified AI memory across every platform and terminal.**

Tapestry is a desktop-like platform that connects apps from every platform and
different CLIs into one place. It contains a single AI agent that remembers
everything from every connected platform — conversations, terminal commands,
file changes, GitHub activity — and talks to you through a continuous,
intelligent conversation that knows your full story.

---

## Features

- **Unified persistent memory** — every event from every platform is stored in
  a single SQLite database so nothing is forgotten
- **Single AI agent** — one conversational agent that recalls your full
  cross-platform history and can answer questions, find memories, and summarise
  your activity
- **Pluggable platform integrations** — terminal/shell history, filesystem
  watcher, GitHub activity, with more adapters easy to add
- **Rich TUI** — a terminal-based UI showing connected platforms and your chat
  with the agent side by side
- **Optional OpenAI backend** — works offline with a built-in responder; set
  `TAPESTRY_OPENAI_KEY` for full GPT-powered responses

---

## Quick start

```bash
pip install tapestry
```

Or from source:

```bash
git clone https://github.com/popeyexz/tapestry-
cd tapestry-
pip install -e .
```

### Chat with the agent

```bash
tapestry chat
```

### Launch the full TUI

```bash
tapestry ui
# with GitHub integration:
tapestry ui --github-token ghp_…
# with filesystem watcher:
tapestry ui --watch ~/projects
```

### Connect a platform

```bash
tapestry connect terminal
tapestry connect filesystem --path ~/projects
tapestry connect github --token ghp_…
```

### Manage memory

```bash
tapestry memory stats
tapestry memory list
tapestry memory search "Python"
tapestry memory add-fact "I prefer dark mode"
tapestry memory clear --source terminal
```

### View your story

```bash
tapestry story
```

---

## Architecture

```
tapestry/
  core/
    memory.py        # SQLite-backed unified memory store
    agent.py         # Conversational AI agent with memory context
    integrations.py  # Integration manager / lifecycle
  integrations/
    base.py          # Abstract base for all platform adapters
    terminal.py      # Shell history + command runner
    filesystem.py    # Directory watcher
    github.py        # GitHub events & notifications
  ui/
    app.py           # Rich-based TUI
  cli.py             # Click CLI entry point
```

---

## Environment variables

| Variable | Description |
|---|---|
| `TAPESTRY_OPENAI_KEY` | OpenAI API key for GPT-powered responses |
| `TAPESTRY_GITHUB_TOKEN` | GitHub Personal Access Token for the GitHub integration |

---

## License

MIT — see [LICENSE](LICENSE).

