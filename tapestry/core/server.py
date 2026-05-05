"""Tapestry HTTP server — exposes the unified memory over HTTP.

Once running, any external app, script, or device can push events into
Tapestry and read them back. This is what makes the memory shared across
every connected platform: a desktop app, a phone client, a chat bot, or a
remote terminal can all talk to the same store.

Endpoints:
    POST /memory          Add an entry (JSON body: source, kind, role, content)
    GET  /memory          List recent entries (?limit=, ?source=, ?kind=)
    GET  /memory/search   Search entries (?q=, ?source=, ?limit=)
    GET  /stats           Memory statistics
    GET  /export          Full JSON export of every memory
    POST /import          Merge a JSON array of entries into the store
    GET  /health          Health check
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from tapestry.core.memory import MemoryEntry, MemoryStore


def make_handler(store: MemoryStore, token: Optional[str] = None):
    """Build an HTTP handler bound to a specific MemoryStore."""

    class TapestryHandler(BaseHTTPRequestHandler):
        server_version = "Tapestry/0.1"

        def log_message(self, fmt, *args):  # silence default stderr logs
            return

        def _auth_ok(self) -> bool:
            if not token:
                return True
            header = self.headers.get("Authorization", "")
            return header == f"Bearer {token}"

        def _send_json(self, status: int, payload) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}

        # ---------------- GET ----------------
        def do_GET(self):
            if not self._auth_ok():
                return self._send_json(401, {"error": "unauthorized"})

            url = urlparse(self.path)
            qs = {k: v[0] for k, v in parse_qs(url.query).items()}

            if url.path == "/health":
                return self._send_json(200, {"ok": True})

            if url.path == "/stats":
                return self._send_json(200, store.stats())

            if url.path == "/export":
                return self._send_json(200, store.export_entries())

            if url.path == "/memory":
                limit = int(qs.get("limit", "50"))
                entries = store.recent(
                    limit=limit,
                    source=qs.get("source"),
                    kind=qs.get("kind"),
                )
                return self._send_json(200, [e.to_dict() for e in entries])

            if url.path == "/memory/search":
                q = qs.get("q", "")
                if not q:
                    return self._send_json(400, {"error": "q is required"})
                entries = store.search(
                    q,
                    source=qs.get("source"),
                    limit=int(qs.get("limit", "20")),
                )
                return self._send_json(200, [e.to_dict() for e in entries])

            return self._send_json(404, {"error": "not found"})

        # ---------------- POST ----------------
        def do_POST(self):
            if not self._auth_ok():
                return self._send_json(401, {"error": "unauthorized"})

            url = urlparse(self.path)

            if url.path == "/memory":
                body = self._read_body()
                content = body.get("content", "")
                if not content:
                    return self._send_json(400, {"error": "content is required"})
                entry = MemoryEntry(
                    source=body.get("source", "external"),
                    kind=body.get("kind", "message"),
                    role=body.get("role", "user"),
                    content=content,
                    metadata=body.get("metadata", {}),
                )
                store.add(entry)
                return self._send_json(201, {"id": entry.id})

            if url.path == "/import":
                body = self._read_body()
                entries = body if isinstance(body, list) else body.get("entries", [])
                if not isinstance(entries, list):
                    return self._send_json(400, {"error": "expected a list"})
                added = store.import_entries(entries)
                return self._send_json(200, {"added": added})

            return self._send_json(404, {"error": "not found"})

    return TapestryHandler


def serve(
    store: MemoryStore,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: Optional[str] = None,
) -> ThreadingHTTPServer:
    """Create (but don't start) a threaded HTTP server bound to *store*."""
    handler_cls = make_handler(store, token=token)
    return ThreadingHTTPServer((host, port), handler_cls)


def serve_forever(
    store: MemoryStore,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: Optional[str] = None,
) -> None:
    """Start the server and block. Ctrl+C to stop."""
    httpd = serve(store, host=host, port=port, token=token)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
