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
  watcher, GitHub activity, Slack messages, with more adapters easy to add
- **Rich TUI** — a terminal-based UI showing connected platforms and your chat
  with the agent side by side
- **Web app** — `tapestry web` launches a browser UI (chat, platform status,
  live memory feed) backed by the same store as the CLI
- **HTTP API** — `tapestry serve` exposes the memory so any app on any device
  can push or read entries; the same memory follows you everywhere
- **Background daemon** — `tapestry daemon` keeps every platform synced
  automatically while you work
- **Portable memory** — `tapestry memory export/import` moves your full
  history between machines as a single JSON file
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

### Launch the web app (browser UI)

```bash
tapestry web
# auto-syncs every platform every 30s and opens your browser:
tapestry web --watch ~/projects --github-token ghp_… --slack-token xoxb-…
# require a login password:
TAPESTRY_WEB_PASSWORD=hunter2 tapestry web
```

The web app is a single-page interface with chat, platform status, and a
live memory feed — same store, same agent, just visible in any browser.

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
tapestry connect slack --token xoxb-…
```

### Run the HTTP API (so any app/device can share the same memory)

```bash
tapestry serve --host 0.0.0.0 --port 8765
# from any other app:
curl -X POST http://host:8765/memory \
     -H 'Content-Type: application/json' \
     -d '{"source":"my-app","content":"user opened settings"}'
curl http://host:8765/memory/search?q=settings
```

### Run the daemon (auto-sync every platform in the background)

```bash
tapestry daemon --interval 30 \
    --watch ~/projects \
    --github-token ghp_… \
    --slack-token xoxb-…
```

### Move your memory between machines

```bash
# laptop:
tapestry memory export ~/tapestry-backup.json
# desktop:
tapestry memory import ~/tapestry-backup.json
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
    memory.py        # SQLite-backed unified memory store + export/import
    agent.py         # Conversational AI agent with memory context
    integrations.py  # Integration manager / lifecycle / daemon loop
    server.py        # HTTP API so any app or device can share memory
  integrations/
    base.py          # Abstract base for all platform adapters
    terminal.py      # Shell history + command runner
    filesystem.py    # Directory watcher
    github.py        # GitHub events & notifications
    slack.py         # Slack channel messages
  ui/
    app.py           # Rich-based TUI
  web/
    index.html       # Single-page browser web app
  cli.py             # Click CLI entry point
```

---

## Environment variables

| Variable | Description |
|---|---|
| `TAPESTRY_OPENAI_KEY` | OpenAI API key for GPT-powered responses |
| `TAPESTRY_GITHUB_TOKEN` | GitHub Personal Access Token for the GitHub integration |
| `TAPESTRY_SLACK_TOKEN` | Slack Bot User OAuth Token (`xoxb-…`) for the Slack integration |
| `TAPESTRY_API_TOKEN` | Optional bearer token enforced by `tapestry serve` |
| `TAPESTRY_WEB_PASSWORD` | Optional login password for the web app |

---

## License

MIT — see [LICENSE](LICENSE).

