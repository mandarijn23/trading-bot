"""Minimal WSGI entrypoint for Vercel Python deployments.

This keeps deploy builds green even when the repository's primary runtime is not a
web framework app. It exposes a simple JSON health response.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def _json_response(status: str, body: dict) -> tuple[str, list[tuple[str, str]], list[bytes]]:
    payload = json.dumps(body, ensure_ascii=True).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(payload))),
    ]
    return status, headers, [payload]


def app(environ, start_response):
    """WSGI callable expected by Vercel.

    Routes:
    - `/`        : basic service metadata
    - `/health`  : health check payload
    """
    path = environ.get("PATH_INFO", "/") or "/"

    if path in ("/", ""):
        status, headers, body = _json_response(
            "200 OK",
            {
                "service": "trading-bot",
                "status": "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    elif path == "/health":
        status, headers, body = _json_response(
            "200 OK",
            {
                "ok": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    else:
        status, headers, body = _json_response(
            "404 Not Found",
            {
                "error": "not_found",
                "path": path,
            },
        )

    start_response(status, headers)
    return body
