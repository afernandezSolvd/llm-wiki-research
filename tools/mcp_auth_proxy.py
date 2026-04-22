#!/usr/bin/env python3
"""
MCP Auth Proxy
Listens on PROXY_PORT (default 8001), forwards every request to UPSTREAM_URL
(default http://localhost:8000) with a transparently-refreshed Bearer token
obtained from the /api/v1/status/bootstrap endpoint.

Token refresh strategy:
  - Token is fetched lazily on first request and cached in memory.
  - Refreshed automatically 5 minutes before expiry.
  - On a 401 from upstream, token is force-refreshed and the request retried once.

No credentials or environment variables needed from MCP clients.
Both stdio (Claude Code) and http (Kiro) MCP transports work identically.
"""
import base64
import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

UPSTREAM = os.getenv("UPSTREAM_URL", "http://localhost:8000")
PROXY_PORT = int(os.getenv("PROXY_PORT", "8001"))
BOOTSTRAP_PATH = "/api/v1/status/bootstrap"
REFRESH_BUFFER_SECS = 300  # refresh 5 min before token expiry

_token: str = ""
_expiry: float = 0.0
_lock = threading.Lock()


def _fetch_token() -> tuple[str, float]:
    url = UPSTREAM + BOOTSTRAP_PATH
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    raw: str = data["access_token"]
    # JWT payload is base64url-encoded; add padding before decoding
    payload_b64 = raw.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    exp = json.loads(base64.urlsafe_b64decode(payload_b64))["exp"]
    return raw, float(exp)


def get_token() -> str:
    global _token, _expiry
    with _lock:
        if time.time() >= _expiry - REFRESH_BUFFER_SECS:
            _token, _expiry = _fetch_token()
            exp_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_expiry))
            print(f"[auth-proxy] token refreshed, expires {exp_str}", flush=True)
    return _token


def force_refresh() -> str:
    global _expiry
    with _lock:
        _expiry = 0.0
    return get_token()


class ProxyHandler(BaseHTTPRequestHandler):

    def _proxy(self, retry: bool = True) -> None:
        try:
            token = get_token()
        except Exception as exc:
            self.send_error(503, f"auth-proxy: cannot fetch token — {exc}")
            return

        body_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(body_len) if body_len else None

        req = urllib.request.Request(
            f"{UPSTREAM}{self.path}",
            data=body,
            method=self.command,
        )
        for key, val in self.headers.items():
            low = key.lower()
            if low in ("host", "authorization", "content-length", "transfer-encoding"):
                continue
            req.add_header(key, val)
        req.add_header("Authorization", f"Bearer {token}")
        if body:
            req.add_header("Content-Length", str(len(body)))

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                for key, val in resp.headers.items():
                    if key.lower() == "transfer-encoding":
                        continue
                    self.send_header(key, val)
                self.end_headers()
                # Stream in chunks — required for SSE query responses
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()

        except urllib.error.HTTPError as exc:
            if exc.code == 401 and retry:
                # Force-refresh token and retry the request exactly once
                force_refresh()
                self._proxy(retry=False)
            else:
                error_body = exc.read()
                self.send_response(exc.code)
                for key, val in exc.headers.items():
                    if key.lower() == "transfer-encoding":
                        continue
                    self.send_header(key, val)
                self.send_header("Content-Length", str(len(error_body)))
                self.end_headers()
                self.wfile.write(error_body)

        except Exception as exc:
            self.send_error(502, f"auth-proxy upstream error: {exc}")

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _proxy

    def log_message(self, fmt, *args) -> None:
        pass  # suppress per-request noise; errors still go to stderr


def _wait_for_api(retries: int = 20, delay: float = 3.0) -> None:
    for attempt in range(retries):
        try:
            get_token()
            return
        except Exception as exc:
            if attempt == retries - 1:
                print(f"[auth-proxy] ERROR: API not ready after {retries} attempts: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"[auth-proxy] waiting for API... ({attempt + 1}/{retries})", flush=True)
            time.sleep(delay)


if __name__ == "__main__":
    _wait_for_api()
    server = HTTPServer(("0.0.0.0", PROXY_PORT), ProxyHandler)
    exp_str = time.strftime("%Y-%m-%d", time.gmtime(_expiry))
    print(
        f"[auth-proxy] ready — :{PROXY_PORT} → {UPSTREAM}  (token valid until {exp_str})",
        flush=True,
    )
    server.serve_forever()
