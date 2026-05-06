"""GitHub integration.

Fetches recent GitHub activity for the authenticated user and ingests it into
Tapestry memory: pull requests, issues, commits, and notifications.

Requires a GitHub Personal Access Token passed as ``token`` to the constructor
or via the ``TAPESTRY_GITHUB_TOKEN`` environment variable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from tapestry.integrations.base import BaseIntegration
from tapestry.core.memory import MemoryStore

_API_BASE = "https://api.github.com"


class GitHubIntegration(BaseIntegration):
    """Pulls GitHub events and notifications into Tapestry memory."""

    name = "github"
    description = "Syncs GitHub activity: PRs, issues, commits, notifications"

    def __init__(
        self,
        memory: Optional[MemoryStore] = None,
        token: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(memory=memory, **kwargs)
        self._token = token or os.environ.get("TAPESTRY_GITHUB_TOKEN", "")
        self._username: str = ""
        self._last_event_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        if not self._token:
            self.status = "no token — set TAPESTRY_GITHUB_TOKEN"
            return
        try:
            user = self._get("/user")
            self._username = user.get("login", "")
            self._mark_connected()
            self.memory.add_event(
                content=f"Connected to GitHub as @{self._username}",
                source=self.name,
                metadata={"username": self._username},
            )
        except Exception as exc:
            self.status = f"connection failed: {exc}"

    def disconnect(self) -> None:
        self._mark_disconnected()

    def sync(self) -> int:
        if not self.connected or not self._username:
            return 0
        count = 0
        count += self._sync_events()
        count += self._sync_notifications()
        return count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _sync_events(self) -> int:
        count = 0
        try:
            events = self._get(
                f"/users/{self._username}/events?per_page=30"
            )
            new_events = []
            for ev in events:
                if ev["id"] == self._last_event_id:
                    break
                new_events.append(ev)
            if new_events:
                self._last_event_id = new_events[0]["id"]
            for ev in reversed(new_events):
                summary = _summarise_event(ev)
                if summary:
                    self.memory.add_event(
                        content=summary,
                        source=self.name,
                        metadata={"event_type": ev.get("type"), "id": ev.get("id")},
                    )
                    count += 1
        except Exception:
            pass
        return count

    def _sync_notifications(self) -> int:
        count = 0
        try:
            notifications = self._get("/notifications?per_page=20")
            for n in notifications:
                subject = n.get("subject", {})
                title = subject.get("title", "(no title)")
                ntype = n.get("reason", "")
                repo = n.get("repository", {}).get("full_name", "")
                content = f"GitHub notification [{ntype}] in {repo}: {title}"
                # Only store if not already in memory
                existing = self.memory.search(content[:60], source=self.name, limit=1)
                if not existing:
                    self.memory.add_event(
                        content=content,
                        source=self.name,
                        metadata={"reason": ntype, "repo": repo},
                    )
                    count += 1
        except Exception:
            pass
        return count

    def _get(self, path: str) -> list | dict:
        url = _API_BASE + path
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {self._token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "tapestry/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())


def _summarise_event(event: dict) -> str:
    etype = event.get("type", "")
    repo = event.get("repo", {}).get("name", "")
    payload = event.get("payload", {})
    if etype == "PushEvent":
        commits = payload.get("commits", [])
        msgs = [c.get("message", "")[:60] for c in commits[:3]]
        return f"Pushed {len(commits)} commit(s) to {repo}: {'; '.join(msgs)}"
    if etype == "PullRequestEvent":
        pr = payload.get("pull_request", {})
        action = payload.get("action", "")
        title = pr.get("title", "")
        return f"PR {action} in {repo}: {title}"
    if etype == "IssuesEvent":
        issue = payload.get("issue", {})
        action = payload.get("action", "")
        title = issue.get("title", "")
        return f"Issue {action} in {repo}: {title}"
    if etype == "CreateEvent":
        ref_type = payload.get("ref_type", "")
        ref = payload.get("ref", "")
        return f"Created {ref_type} '{ref}' in {repo}"
    if etype == "WatchEvent":
        return f"Starred {repo}"
    if etype == "ForkEvent":
        return f"Forked {repo}"
    return ""
