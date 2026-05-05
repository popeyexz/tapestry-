"""Tests for the Tapestry HTTP API server."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from tapestry.core.memory import MemoryStore
from tapestry.core.server import serve


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "server.db")


@pytest.fixture()
def server(store: MemoryStore):
    httpd = serve(store, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://{httpd.server_address[0]}:{httpd.server_address[1]}"
    yield base, store
    httpd.shutdown()
    httpd.server_close()


def _get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def _post(url: str, body: dict, headers: dict | None = None):
    data = json.dumps(body).encode()
    headers = {**(headers or {}), "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


class TestHealth:
    def test_health(self, server):
        base, _ = server
        status, body = _get(f"{base}/health")
        assert status == 200
        assert body == {"ok": True}


class TestMemoryEndpoints:
    def test_post_then_list(self, server):
        base, store = server
        status, body = _post(
            f"{base}/memory",
            {"content": "from external app", "source": "desktop", "kind": "event"},
        )
        assert status == 201
        assert "id" in body

        status, body = _get(f"{base}/memory")
        assert status == 200
        assert any(e["content"] == "from external app" for e in body)

    def test_post_requires_content(self, server):
        base, _ = server
        with pytest.raises(urllib.error.HTTPError):
            _post(f"{base}/memory", {"source": "x"})

    def test_search(self, server):
        base, store = server
        store.add_message("python is great", source="chat")
        store.add_message("not relevant", source="chat")
        status, body = _get(f"{base}/memory/search?q=python")
        assert status == 200
        assert len(body) == 1
        assert "python" in body[0]["content"]

    def test_stats(self, server):
        base, store = server
        store.add_message("a", source="chat")
        store.add_event("b", source="github")
        status, body = _get(f"{base}/stats")
        assert status == 200
        assert body["total"] == 2

    def test_export_then_import_roundtrip(self, tmp_path: Path):
        src = MemoryStore(db_path=tmp_path / "src.db")
        src.add_message("hello", source="chat")
        src.add_event("commit", source="github")

        dst = MemoryStore(db_path=tmp_path / "dst.db")
        n = dst.import_entries(src.export_entries())
        assert n == 2
        assert dst.stats()["total"] == 2

        # Re-import is idempotent (same ids → skipped)
        n2 = dst.import_entries(src.export_entries())
        assert n2 == 0


class TestAuth:
    def test_token_required(self, store, tmp_path):
        httpd = serve(store, host="127.0.0.1", port=0, token="secret")
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://{httpd.server_address[0]}:{httpd.server_address[1]}"
        try:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                _get(f"{base}/stats")
            assert exc_info.value.code == 401

            status, body = _get(
                f"{base}/stats", headers={"Authorization": "Bearer secret"}
            )
            assert status == 200
        finally:
            httpd.shutdown()
            httpd.server_close()


# Required for the urllib.error import above
import urllib.error  # noqa: E402
