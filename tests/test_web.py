"""Tests for the Tapestry web app: HTML serving, sessions, /chat, /greet, /platforms."""

from __future__ import annotations

import http.cookiejar
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tapestry.core.agent import Agent
from tapestry.core.integrations import IntegrationManager
from tapestry.core.memory import MemoryStore
from tapestry.core.server import serve
from tapestry.integrations.base import BaseIntegration


class _FakeIntegration(BaseIntegration):
    name = "fake"
    description = "fake"

    def connect(self): self._mark_connected()
    def disconnect(self): self._mark_disconnected()
    def sync(self): return 0


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "web.db")


@pytest.fixture()
def agent(store: MemoryStore) -> Agent:
    return Agent(memory=store)


def _start(httpd):
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return f"http://{httpd.server_address[0]}:{httpd.server_address[1]}"


def _client():
    """A urllib opener that keeps cookies between requests."""
    jar = http.cookiejar.CookieJar()
    handler = urllib.request.HTTPCookieProcessor(jar)
    return urllib.request.build_opener(handler), jar


def _get(opener, url):
    with opener.open(url, timeout=5) as resp:
        return resp.status, resp.read(), resp.headers


def _post_json(opener, url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with opener.open(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


# ---------------------------------------------------------------------------
# HTML serving
# ---------------------------------------------------------------------------

class TestHTML:
    def test_index_served(self, store):
        httpd = serve(store, host="127.0.0.1", port=0)
        base = _start(httpd)
        try:
            opener, _ = _client()
            status, body, headers = _get(opener, f"{base}/")
            assert status == 200
            assert b"Tapestry" in body
            assert "text/html" in headers.get("Content-Type", "")
        finally:
            httpd.shutdown(); httpd.server_close()


# ---------------------------------------------------------------------------
# Login + sessions
# ---------------------------------------------------------------------------

class TestLogin:
    def test_no_password_open_access(self, store, agent):
        httpd = serve(store, host="127.0.0.1", port=0, agent=agent)
        base = _start(httpd)
        try:
            opener, _ = _client()
            status, body = _post_json(opener, f"{base}/chat", {"message": "hi"})
            assert status == 200
            assert "reply" in body
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_password_required(self, store, agent):
        httpd = serve(
            store, host="127.0.0.1", port=0, password="hunter2", agent=agent
        )
        base = _start(httpd)
        try:
            opener, _ = _client()
            with pytest.raises(urllib.error.HTTPError) as exc:
                _post_json(opener, f"{base}/chat", {"message": "hi"})
            assert exc.value.code == 401
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_wrong_password_rejected(self, store, agent):
        httpd = serve(
            store, host="127.0.0.1", port=0, password="hunter2", agent=agent
        )
        base = _start(httpd)
        try:
            opener, _ = _client()
            with pytest.raises(urllib.error.HTTPError) as exc:
                _post_json(opener, f"{base}/login", {"password": "wrong"})
            assert exc.value.code == 401
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_login_then_chat_works(self, store, agent):
        httpd = serve(
            store, host="127.0.0.1", port=0, password="hunter2", agent=agent
        )
        base = _start(httpd)
        try:
            opener, jar = _client()
            status, body = _post_json(
                opener, f"{base}/login", {"password": "hunter2"}
            )
            assert status == 200
            assert any(c.name == "tapestry_session" for c in jar)

            status, body = _post_json(opener, f"{base}/chat", {"message": "hi"})
            assert status == 200
            assert isinstance(body["reply"], str)
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_logout_clears_session(self, store, agent):
        httpd = serve(
            store, host="127.0.0.1", port=0, password="hunter2", agent=agent
        )
        base = _start(httpd)
        try:
            opener, _ = _client()
            _post_json(opener, f"{base}/login", {"password": "hunter2"})
            _post_json(opener, f"{base}/logout", {})
            with pytest.raises(urllib.error.HTTPError) as exc:
                _post_json(opener, f"{base}/chat", {"message": "hi"})
            assert exc.value.code == 401
        finally:
            httpd.shutdown(); httpd.server_close()


# ---------------------------------------------------------------------------
# Web endpoints: /greet, /chat, /platforms
# ---------------------------------------------------------------------------

class TestEndpoints:
    def test_greet(self, store, agent):
        httpd = serve(store, host="127.0.0.1", port=0, agent=agent)
        base = _start(httpd)
        try:
            opener, _ = _client()
            with opener.open(f"{base}/greet", timeout=5) as resp:
                payload = json.loads(resp.read())
            assert "greeting" in payload
            assert "Tapestry" in payload["greeting"]
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_chat_persists_messages(self, store, agent):
        httpd = serve(store, host="127.0.0.1", port=0, agent=agent)
        base = _start(httpd)
        try:
            opener, _ = _client()
            _post_json(opener, f"{base}/chat", {"message": "remember purple"})
            entries = store.recent(source="web", kind="message")
            contents = [e.content for e in entries]
            assert any("purple" in c for c in contents)
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_platforms(self, store, agent):
        manager = IntegrationManager(memory=store)
        manager.register(_FakeIntegration)
        manager.start_all()
        httpd = serve(store, host="127.0.0.1", port=0, agent=agent, manager=manager)
        base = _start(httpd)
        try:
            opener, _ = _client()
            with opener.open(f"{base}/platforms", timeout=5) as resp:
                report = json.loads(resp.read())
            assert any(p["name"] == "fake" and p["connected"] for p in report)
        finally:
            httpd.shutdown(); httpd.server_close()
