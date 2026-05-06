"""Tests for tapestry.core.agent."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapestry.core.agent import Agent, _fmt_ts, _source_icon
from tapestry.core.memory import MemoryStore


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "agent_test.db")


@pytest.fixture()
def agent(store: MemoryStore) -> Agent:
    return Agent(memory=store)


class TestAgentGreet:
    def test_greeting_empty_memory(self, agent: Agent):
        greeting = agent.greet()
        assert "Tapestry" in greeting

    def test_greeting_with_memory(self, agent: Agent):
        agent.memory.add_message("hello", source="chat")
        agent.memory.add_event("PR opened", source="github")
        greeting = agent.greet()
        assert "memories" in greeting.lower()


class TestAgentChat:
    def test_chat_persists_user_message(self, agent: Agent):
        agent.chat("test message")
        history = agent.memory.conversation_history(source="chat")
        user_msgs = [e for e in history if e.role == "user"]
        assert any("test message" in e.content for e in user_msgs)

    def test_chat_persists_assistant_reply(self, agent: Agent):
        agent.chat("hello")
        history = agent.memory.conversation_history(source="chat")
        assistant_msgs = [e for e in history if e.role == "assistant"]
        assert len(assistant_msgs) >= 1

    def test_chat_returns_string(self, agent: Agent):
        reply = agent.chat("anything")
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_chat_custom_source(self, agent: Agent):
        agent.chat("from terminal", source="terminal")
        entries = agent.memory.recent(source="terminal", kind="message")
        assert len(entries) == 2  # user + assistant


class TestAgentRecall:
    def test_recall_finds_stored_memories(self, agent: Agent):
        agent.memory.add_message("I love Python")
        results = agent.recall("Python")
        assert len(results) >= 1
        assert any("Python" in e.content for e in results)

    def test_recall_empty(self, agent: Agent):
        results = agent.recall("xyz_definitely_not_there")
        assert results == []


class TestAgentStory:
    def test_story_empty(self, agent: Agent):
        s = agent.story()
        assert "No memories" in s or "Connect" in s

    def test_story_with_memories(self, agent: Agent):
        agent.memory.add_event("Pushed code to main", source="github")
        agent.memory.add_message("Reviewed PR #7", source="chat")
        s = agent.story()
        assert "story" in s.lower() or "github" in s or "Pushed" in s


class TestAgentBuiltinReplies:
    def test_stats_reply(self, agent: Agent):
        agent.memory.add_message("hello", source="chat")
        reply = agent.chat("how many memories do you have?")
        assert "memor" in reply.lower() or "total" in reply.lower()

    def test_summary_reply(self, agent: Agent):
        agent.memory.add_event("Built the project", source="terminal")
        reply = agent.chat("give me a summary")
        # Should get story or some relevant reply
        assert isinstance(reply, str) and len(reply) > 10

    def test_recall_reply(self, agent: Agent):
        agent.memory.add_fact("User uses vim")
        reply = agent.chat("recall vim")
        assert isinstance(reply, str)

    def test_forget_reply(self, agent: Agent):
        reply = agent.chat("forget everything")
        assert "tapestry memory clear" in reply or "clear" in reply.lower()


class TestUtilities:
    def test_fmt_ts_valid(self):
        ts = "2025-01-15T14:30:00+00:00"
        result = _fmt_ts(ts)
        assert "2025-01-15" in result

    def test_fmt_ts_invalid(self):
        result = _fmt_ts("not-a-date")
        assert result == "not-a-date"

    def test_source_icon_known(self):
        assert _source_icon("github") == "🐙"
        assert _source_icon("chat") == "💬"
        assert _source_icon("terminal") == "🖥️"

    def test_source_icon_unknown(self):
        icon = _source_icon("mystery_platform")
        assert icon == "🔌"
