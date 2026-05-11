# uipro

Connect apps from every platform and terminal CLI in one unified interface.

## What uipro does

uipro is a platform that bridges tools from different CLIs, terminals, and AI assistants so you can use them together seamlessly. It installs integration skills into AI assistants and manages cross-platform CLI workflows.

## Usage

```bash
uipro init --ai claude --global   # Install to ~/.claude/skills/
uipro --help
```

## Commands

### init

Install the uipro skill into an AI assistant's skills directory.

```bash
uipro init --ai claude [--global]
```

**Options:**
- `--ai claude` — Target AI assistant
- `--global` — Install to the home directory (`~/.claude/skills/`); omit to install into the current project

## When to invoke this skill

Use this skill when the user:
- Wants to set up uipro in their AI assistant environment
- Needs to bridge commands or tools across different CLIs
- Asks about installing or initializing uipro
- Mentions cross-platform CLI integration

## Installation

```bash
npm install -g uipro
```
