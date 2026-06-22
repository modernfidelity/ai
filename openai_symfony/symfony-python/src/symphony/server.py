"""Optional HTTP server extension (Section 13.7)."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

from . import log

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

try:
    from aiohttp import web
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False


def _json_response(data: Any, status: int = 200):
    from aiohttp import web
    return web.Response(
        text=json.dumps(data, default=str),
        status=status,
        content_type="application/json",
    )


def _error_response(code: str, message: str, status: int = 400):
    return _json_response({"error": {"code": code, "message": message}}, status=status)


async def make_app(orchestrator: "Orchestrator") -> "web.Application":
    from aiohttp import web

    app = web.Application()

    async def handle_state(request: web.Request) -> web.Response:
        return _json_response(orchestrator.snapshot())

    async def handle_issue(request: web.Request) -> web.Response:
        identifier = request.match_info["identifier"]
        detail = orchestrator.issue_detail(identifier)
        if detail is None:
            return _error_response(
                "issue_not_found",
                f"Issue '{identifier}' not found in current in-memory state",
                status=404,
            )
        return _json_response(detail)

    async def handle_refresh(request: web.Request) -> web.Response:
        from datetime import datetime, timezone
        orchestrator.trigger_refresh()
        return _json_response(
            {
                "queued": True,
                "coalesced": False,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "operations": ["poll", "reconcile"],
            },
            status=202,
        )

    async def handle_dashboard(request: web.Request) -> web.Response:
        snapshot = orchestrator.snapshot()
        html = _render_dashboard(snapshot)
        from aiohttp import web as w
        return w.Response(text=html, content_type="text/html")

    app.router.add_get("/", handle_dashboard)
    app.router.add_get("/api/v1/state", handle_state)
    app.router.add_get("/api/v1/{identifier}", handle_issue)
    app.router.add_post("/api/v1/refresh", handle_refresh)

    return app


async def start_server(orchestrator: "Orchestrator", port: int) -> Any:
    if not _AIOHTTP_AVAILABLE:
        log.warn("aiohttp not available; HTTP server extension disabled")
        return None

    from aiohttp import web
    app = await make_app(orchestrator)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    actual_port = site._server.sockets[0].getsockname()[1]
    log.info(f"http_server started port={actual_port}")
    return runner


def _render_dashboard(snapshot: dict) -> str:
    running = snapshot.get("running", [])
    retrying = snapshot.get("retrying", [])
    totals = snapshot.get("codex_totals", {})
    config_error = snapshot.get("config_error")

    error_banner = (
        f'<div class="error">Config error: {config_error}</div>'
        if config_error
        else ""
    )

    running_rows = "".join(
        f"<tr><td>{r['issue_identifier']}</td><td>{r['state']}</td>"
        f"<td>{r['turn_count']}</td><td>{r.get('last_event','')}</td>"
        f"<td>{r['started_at']}</td></tr>"
        for r in running
    )

    retrying_rows = "".join(
        f"<tr><td>{r['issue_identifier']}</td><td>{r['attempt']}</td>"
        f"<td>{r['due_at']}</td><td>{r.get('error','')}</td></tr>"
        for r in retrying
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <title>Symphony</title>
  <meta http-equiv="refresh" content="10">
  <style>
    body{{font-family:monospace;margin:2em}}
    table{{border-collapse:collapse;width:100%}}
    th,td{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
    th{{background:#f0f0f0}}
    .error{{color:red;font-weight:bold;margin-bottom:1em}}
    h2{{margin-top:1.5em}}
  </style>
</head>
<body>
  <h1>Symphony</h1>
  {error_banner}
  <p>Generated: {snapshot.get('generated_at','')} &mdash;
     Running: {snapshot['counts']['running']} &mdash;
     Retrying: {snapshot['counts']['retrying']}</p>
  <h2>Running</h2>
  <table>
    <tr><th>Issue</th><th>State</th><th>Turns</th><th>Last Event</th><th>Started</th></tr>
    {running_rows or '<tr><td colspan="5">None</td></tr>'}
  </table>
  <h2>Retrying</h2>
  <table>
    <tr><th>Issue</th><th>Attempt</th><th>Due At</th><th>Error</th></tr>
    {retrying_rows or '<tr><td colspan="4">None</td></tr>'}
  </table>
  <h2>Token Totals</h2>
  <pre>{json.dumps(totals, indent=2)}</pre>
</body>
</html>"""
