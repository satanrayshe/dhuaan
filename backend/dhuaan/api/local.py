"""Local dev server on :8787 wrapping the Lambda handler (stdlib only).

uv run python -m dhuaan.api.local [--port 8787] [--store <dir containing latest/>]
"""
from __future__ import annotations

import argparse
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

from dhuaan.api.handler import handler


def to_event(method: str, path: str, headers: dict, body: bytes, client_ip: str) -> dict:
    u = urlsplit(path)
    return {
        "version": "2.0", "rawPath": u.path, "rawQueryString": u.query,
        "queryStringParameters": dict(parse_qsl(u.query)) or None,
        "headers": {k.lower(): v for k, v in headers.items()},
        "requestContext": {"http": {"method": method, "path": u.path, "sourceIp": client_ip}},
        "body": body.decode("utf-8", "replace") if body else None, "isBase64Encoded": False,
    }


class _H(BaseHTTPRequestHandler):
    server_version = "dhuaan-local/0.1"

    def _do(self) -> None:
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n else b""
        resp = handler(to_event(self.command, self.path, dict(self.headers), body, self.client_address[0]))
        out = (resp.get("body") or "").encode("utf-8")
        self.send_response(resp["statusCode"])
        for k, v in resp.get("headers", {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        if out and self.command != "HEAD":
            self.wfile.write(out)

    do_GET = do_POST = do_OPTIONS = _do


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--store", help="directory containing latest/ (default: settings.local_out)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if a.store:
        from dhuaan.agent import data
        from dhuaan.store import LocalStore
        data.use_store(LocalStore(a.store))
    srv = ThreadingHTTPServer((a.host, a.port), _H)
    print(f"Dhuaan API on http://{a.host}:{a.port}/api/health")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
