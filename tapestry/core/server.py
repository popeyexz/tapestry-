"""Tapestry HTTP server — exposes the unified memory and the web UI.

Once running, any external app, script, or device can push events into
Tapestry and read them back. A browser pointed at the same URL gets the
full Tapestry web app — chat, platform status, and memory feed — sharing
the exact same store as the CLI and every connected platform.

Auth modes
----------
* No password configured → open access (default for `--host 127.0.0.1`).
* Password configured → cookie session: POST /login with {"password": …}
  sets a `tapestry_session` cookie used for every subsequent request.
* Bearer token configured → API clients send ``Authorization: Bearer <token>``.

Endpoints
---------
GET  /                  Web UI (HTML)
GET  /health            Liveness check (no auth)
POST /login             Exchange password for session cookie
POST /logout            Clear session cookie
GET  /greet             Agent greeting message
POST /chat              Send a message, get the agent's reply
GET  /platforms         Status of every registered integration
GET  /stats             Memory statistics
GET  /memory            Recent memory entries
GET  /memory/search     Search memory (?q=…)
POST /memory            Append a single memory entry
GET  /export            Full JSON export
POST /import            Merge a JSON array of entries
"""

from __future__ import annotations

import http.cookies
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from tapestry.core.memory import MemoryEntry, MemoryStore

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def make_handler(
    store: MemoryStore,
    token: Optional[str] = None,
    password: Optional[str] = None,
    agent=None,
    manager=None,
):
    """Build an HTTP handler bound to a specific store (and optionally agent)."""

    sessions: set[str] = set()

    class TapestryHandler(BaseHTTPRequestHandler):
        server_version = "Tapestry/0.1"

        def log_message(self, fmt, *args):  # silence default stderr logs
            return

        # ----------------------------- auth -----------------------------

        def _has_session(self) -> bool:
            cookies = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            sid = cookies.get("tapestry_session")
            return bool(sid and sid.value in sessions)

        def _has_bearer(self) -> bool:
            if not token:
                return False
            return self.headers.get("Authorization", "") == f"Bearer {token}"

        def _auth_ok(self) -> bool:
            # Fully open if no auth at all configured
            if not password and not token:
                return True
            return self._has_session() or self._has_bearer()

        # ---------------------------- helpers ----------------------------

        def _send_json(self, status: int, payload, extra_headers=None) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra_headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: int, html: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def _read_body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}

        # ------------------------------ GET ------------------------------

        def do_GET(self):
            url = urlparse(self.path)
            qs = {k: v[0] for k, v in parse_qs(url.query).items()}

            # Public routes
            if url.path == "/health":
                return self._send_json(200, {"ok": True})
            if url.path in ("/", "/index.html"):
                index = _WEB_DIR / "index.html"
                if index.exists():
                    return self._send_html(200, index.read_bytes())
                return self._send_html(
                    404, b"<h1>Tapestry web UI not installed</h1>"
                )

            if not self._auth_ok():
                return self._send_json(401, {"error": "unauthorized"})

            if url.path == "/greet" and agent is not None:
                return self._send_json(200, {"greeting": agent.greet()})

            if url.path == "/platforms":
                report = manager.status_report() if manager else []
                return self._send_json(200, report)

            if url.path == "/stats":
                return self._send_json(200, store.stats())

            if url.path == "/export":
                return self._send_json(200, store.export_entries())

            if url.path == "/memory":
                limit = int(qs.get("limit", "50"))
                entries = store.recent(
                    limit=limit, source=qs.get("source"), kind=qs.get("kind")
                )
                return self._send_json(200, [e.to_dict() for e in entries])

            if url.path == "/memory/search":
                q = qs.get("q", "")
                if not q:
                    return self._send_json(400, {"error": "q is required"})
                entries = store.search(
                    q, source=qs.get("source"), limit=int(qs.get("limit", "20"))
                )
                return self._send_json(200, [e.to_dict() for e in entries])

            return self._send_json(404, {"error": "not found"})

        # ----------------------------- POST ------------------------------

        def do_POST(self):
            url = urlparse(self.path)

            # Login is public so the browser can obtain a session cookie
            if url.path == "/login":
                body = self._read_body()
                if not password:
                    # No password configured — issue a session anyway
                    sid = secrets.token_urlsafe(24)
                    sessions.add(sid)
                    cookie = (
                        f"tapestry_session={sid}; HttpOnly; Path=/; SameSite=Lax"
                    )
                    return self._send_json(
                        200, {"ok": True}, extra_headers={"Set-Cookie": cookie}
                    )
                if body.get("password") != password:
                    return self._send_json(401, {"error": "wrong password"})
                sid = secrets.token_urlsafe(24)
                sessions.add(sid)
                cookie = f"tapestry_session={sid}; HttpOnly; Path=/; SameSite=Lax"
                return self._send_json(
                    200, {"ok": True}, extra_headers={"Set-Cookie": cookie}
                )

            if url.path == "/logout":
                cookies = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
                sid = cookies.get("tapestry_session")
                if sid and sid.value in sessions:
                    sessions.discard(sid.value)
                cookie = "tapestry_session=; HttpOnly; Path=/; Max-Age=0"
                return self._send_json(
                    200, {"ok": True}, extra_headers={"Set-Cookie": cookie}
                )

            if not self._auth_ok():
                return self._send_json(401, {"error": "unauthorized"})

            if url.path == "/chat" and agent is not None:
                body = self._read_body()
                msg = (body.get("message") or "").strip()
                if not msg:
                    return self._send_json(400, {"error": "message is required"})
                reply = agent.chat(msg, source=body.get("source", "web"))
                return self._send_json(200, {"reply": reply})

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
    password: Optional[str] = None,
    agent=None,
    manager=None,
) -> ThreadingHTTPServer:
    """Create (but don't start) a threaded HTTP server."""
    handler_cls = make_handler(
        store, token=token, password=password, agent=agent, manager=manager
    )
    return ThreadingHTTPServer((host, port), handler_cls)


def serve_forever(
    store: MemoryStore,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: Optional[str] = None,
    password: Optional[str] = None,
    agent=None,
    manager=None,
) -> None:
    """Start the server and block. Ctrl+C to stop."""
    httpd = serve(
        store,
        host=host,
        port=port,
        token=token,
        password=password,
        agent=agent,
        manager=manager,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
