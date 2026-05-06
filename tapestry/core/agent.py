"""Tapestry AI Agent — your single persistent intelligence across every platform.

The agent has access to the unified memory store and can:
- Recall past conversations and events from any connected platform
- Answer questions using stored context
- Generate narrative summaries of your cross-platform story
- Accept an optional OpenAI backend (set TAPESTRY_OPENAI_KEY env var)
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import List, Optional

from tapestry.core.memory import MemoryEntry, MemoryStore

# Greeting shown at the start of a new session
_GREETING = (
    "Hello! I'm your Tapestry agent — I remember everything from every platform "
    "you've connected. Ask me anything, tell me to recall a conversation, look up "
    "an event, or just chat."
)

# Commands the agent recognises without an LLM
_CMD_RECALL = re.compile(r"\b(recall|remember|show|find|search|look up)\b", re.I)
_CMD_SUMMARY = re.compile(r"\b(summar[iy]|story|history|what happened|overview)\b", re.I)
_CMD_STATS = re.compile(r"\b(stat[s]?|how many|count|total)\b", re.I)
_CMD_FORGET = re.compile(r"\bforget\b", re.I)


class Agent:
    """Conversational agent backed by Tapestry's unified memory.

    If *TAPESTRY_OPENAI_KEY* is set the agent delegates to GPT; otherwise it
    uses a lightweight built-in responder so Tapestry works out of the box.
    """

    def __init__(
        self,
        memory: Optional[MemoryStore] = None,
        openai_api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.memory = memory or MemoryStore()
        self.model = model
        self._api_key = openai_api_key or os.environ.get("TAPESTRY_OPENAI_KEY", "")
        self._openai_client = None

        if self._api_key:
            try:
                from openai import OpenAI  # type: ignore[import]

                self._openai_client = OpenAI(api_key=self._api_key)
            except ImportError:
                pass  # openai package not installed — fall back gracefully

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def greet(self) -> str:
        """Return a personalised greeting, hinting at stored memory."""
        stats = self.memory.stats()
        total = stats.get("total", 0)
        if total == 0:
            return _GREETING
        sources = list(stats.get("by_source", {}).keys())
        src_str = ", ".join(sources[:4])
        return (
            f"Welcome back! I have {total} memories stored across your platforms "
            f"({src_str}{'…' if len(sources) > 4 else ''}). "
            "What would you like to explore today?"
        )

    def chat(self, user_input: str, source: str = "chat") -> str:
        """Process a user message, persist it, and return the agent reply."""
        # Persist user message
        self.memory.add_message(content=user_input, role="user", source=source)

        # Generate response
        if self._openai_client:
            reply = self._openai_reply(user_input)
        else:
            reply = self._builtin_reply(user_input)

        # Persist assistant reply
        self.memory.add_message(content=reply, role="assistant", source=source)
        return reply

    def recall(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """Search memory and return matching entries."""
        return self.memory.search(query, limit=limit)

    def story(self, limit: int = 30) -> str:
        """Generate a narrative summary of recent cross-platform activity."""
        entries = self.memory.recent(limit=limit)
        if not entries:
            return "No memories yet. Connect some platforms and start using Tapestry!"

        lines: List[str] = ["Here's your Tapestry story so far:\n"]
        for entry in entries:
            ts = _fmt_ts(entry.timestamp)
            icon = _source_icon(entry.source)
            lines.append(f"  {icon} [{ts}] ({entry.source}) {entry.content[:120]}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _builtin_reply(self, user_input: str) -> str:
        """Rule-based responder — works without any API key."""
        text = user_input.strip()

        if _CMD_STATS.search(text):
            return self._stats_reply()

        if _CMD_SUMMARY.search(text):
            return self.story()

        if _CMD_RECALL.search(text):
            # Extract the search term after the command word
            parts = re.split(_CMD_RECALL, text, maxsplit=1)
            query = parts[-1].strip().strip("?").strip()
            if not query:
                query = text
            entries = self.recall(query)
            if not entries:
                return f"I couldn't find anything matching '{query}' in your memory."
            lines = [f"Found {len(entries)} memories for '{query}':\n"]
            for e in entries:
                ts = _fmt_ts(e.timestamp)
                icon = _source_icon(e.source)
                lines.append(f"  {icon} [{ts}] [{e.source}] {e.content[:140]}")
            return "\n".join(lines)

        if _CMD_FORGET.search(text):
            return (
                "To clear memories, use the CLI: `tapestry memory clear`.\n"
                "You can clear all memories or memories from a specific platform."
            )

        # Contextual fallback: search memory for relevant snippets
        entries = self.recall(text, limit=5)
        history = self.memory.conversation_history(limit=8)

        if entries:
            snippets = "\n".join(
                f"  [{e.source}] {e.content[:100]}" for e in entries[:3]
            )
            return (
                f"Based on my memory, here's what I know about that:\n{snippets}\n\n"
                "Connect an OpenAI key (TAPESTRY_OPENAI_KEY) for richer responses."
            )

        if history:
            return (
                "I don't have specific memories about that yet, but I'm here and "
                "learning. Tell me more, and I'll remember it across all your platforms!"
            )

        return (
            "I'm Tapestry — your unified memory across every platform. "
            "I'm running in offline mode right now. Set TAPESTRY_OPENAI_KEY for "
            "full AI responses, or keep chatting to build up my memory!"
        )

    def _openai_reply(self, user_input: str) -> str:
        """Delegate to OpenAI with memory-enriched system prompt."""
        history = self.memory.conversation_history(limit=20)
        facts = self.memory.recent(limit=10, kind="fact")
        events = self.memory.recent(limit=10, kind="event")

        system_parts = [
            "You are Tapestry — a unified AI assistant that remembers everything "
            "from every platform and application the user has connected. "
            "You have access to the user's full cross-platform history below. "
            "Speak naturally, recall details proactively, and help the user make "
            "sense of their cross-platform life.",
        ]
        if facts:
            system_parts.append("\n## Stored facts about the user:")
            for f in facts:
                system_parts.append(f"  - {f.content}")
        if events:
            system_parts.append("\n## Recent platform events:")
            for e in events:
                ts = _fmt_ts(e.timestamp)
                system_parts.append(f"  [{e.source} @ {ts}] {e.content}")

        system_prompt = "\n".join(system_parts)

        messages = [{"role": "system", "content": system_prompt}]
        for entry in history[:-1]:  # exclude the message we just added
            messages.append({"role": entry.role, "content": entry.content})
        messages.append({"role": "user", "content": user_input})

        try:
            response = self._openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=800,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            return f"[OpenAI error: {exc}]\n" + self._builtin_reply(user_input)

    def _stats_reply(self) -> str:
        stats = self.memory.stats()
        total = stats.get("total", 0)
        by_source = stats.get("by_source", {})
        by_kind = stats.get("by_kind", {})
        lines = [f"I have {total} memories stored in total."]
        if by_source:
            lines.append("\nBy platform:")
            for src, n in by_source.items():
                lines.append(f"  {_source_icon(src)} {src}: {n}")
        if by_kind:
            lines.append("\nBy type:")
            for kind, n in by_kind.items():
                lines.append(f"  · {kind}: {n}")
        return "\n".join(lines)


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _fmt_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _source_icon(source: str) -> str:
    icons = {
        "chat": "💬",
        "github": "🐙",
        "terminal": "🖥️",
        "filesystem": "📁",
        "slack": "💼",
        "notion": "📝",
        "tapestry": "🧵",
    }
    return icons.get(source.lower(), "🔌")
