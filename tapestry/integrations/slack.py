"""Slack integration.

Pulls recent Slack messages from channels the bot/user is a member of and
records them as Tapestry memory events. This lets the agent recall what was
discussed on Slack alongside terminal commands and GitHub activity.

Requires a Slack token (Bot User OAuth Token, ``xoxb-…``) passed as ``token``
or via the ``TAPESTRY_SLACK_TOKEN`` environment variable. The integration
talks directly to the Slack Web API over HTTPS — no extra dependency needed.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from tapestry.integrations.base import BaseIntegration
from tapestry.core.memory import MemoryStore

_API_BASE = "https://slack.com/api"


class SlackIntegration(BaseIntegration):
    """Reads Slack channel history into Tapestry memory."""

    name = "slack"
    description = "Captures Slack channel messages"

    def __init__(
        self,
        memory: Optional[MemoryStore] = None,
        token: Optional[str] = None,
        channel_limit: int = 10,
        message_limit: int = 20,
        **kwargs,
    ) -> None:
        super().__init__(memory=memory, **kwargs)
        self._token = token or os.environ.get("TAPESTRY_SLACK_TOKEN", "")
        self._channel_limit = channel_limit
        self._message_limit = message_limit
        self._user_id: str = ""
        self._last_ts: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        if not self._token:
            self.status = "no token — set TAPESTRY_SLACK_TOKEN"
            return
        try:
            data = self._call("auth.test")
            if not data.get("ok"):
                self.status = f"auth failed: {data.get('error', 'unknown')}"
                return
            self._user_id = data.get("user_id", "")
            self._mark_connected()
            self.memory.add_event(
                content=f"Connected to Slack as {data.get('user', '?')}",
                source=self.name,
                metadata={"user_id": self._user_id, "team": data.get("team", "")},
            )
        except Exception as exc:
            self.status = f"connection failed: {exc}"

    def disconnect(self) -> None:
        self._mark_disconnected()

    def sync(self) -> int:
        if not self.connected:
            return 0
        count = 0
        try:
            channels = self._list_channels()
            for ch in channels[: self._channel_limit]:
                count += self._sync_channel(ch)
        except Exception as exc:
            self.status = f"sync error: {exc}"
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _list_channels(self) -> list[dict]:
        data = self._call(
            "conversations.list",
            {"types": "public_channel,private_channel", "exclude_archived": "true"},
        )
        return data.get("channels", []) if data.get("ok") else []

    def _sync_channel(self, channel: dict) -> int:
        cid = channel.get("id", "")
        cname = channel.get("name", cid)
        if not cid:
            return 0
        params: dict = {"channel": cid, "limit": str(self._message_limit)}
        if self._last_ts.get(cid):
            params["oldest"] = self._last_ts[cid]
        data = self._call("conversations.history", params)
        if not data.get("ok"):
            return 0
        messages = data.get("messages", [])
        added = 0
        for msg in reversed(messages):  # chronological
            text = (msg.get("text") or "").strip()
            if not text or msg.get("subtype") in {"channel_join", "channel_leave"}:
                continue
            user = msg.get("user", "?")
            self.memory.add_event(
                content=f"[#{cname}] {user}: {text}",
                source=self.name,
                metadata={
                    "channel": cname,
                    "channel_id": cid,
                    "user": user,
                    "ts": msg.get("ts", ""),
                },
            )
            added += 1
        if messages:
            # Track the most recent ts so next sync only fetches newer ones
            newest = max(m.get("ts", "") for m in messages)
            if newest:
                self._last_ts[cid] = newest
        return added

    def _call(self, method: str, params: Optional[dict] = None) -> dict:
        url = f"{_API_BASE}/{method}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "tapestry/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
