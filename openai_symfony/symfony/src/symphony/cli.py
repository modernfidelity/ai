"""CLI entry point for Symphony."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click

from . import log
from .config import validate_dispatch_config
from .orchestrator import Orchestrator
from .workflow import WorkflowError, WorkflowWatcher, load_workflow_and_config


@click.command(name="symphony")
@click.argument("workflow_path", default="WORKFLOW.md", required=False)
@click.option("--port", default=None, type=int, help="Enable HTTP server on this port")
def main(workflow_path: str, port: Optional[int]) -> None:
    """
    Symphony — coding agent orchestration service.

    WORKFLOW_PATH defaults to ./WORKFLOW.md.

    Trust and safety posture (this implementation):
      - Approval policy: auto-approve (high-trust environment assumed)
      - User-input-required turns: fail immediately
      - Sandbox: implementation-defined (passed through to codex)
      - Workspace isolation enforced via path prefix checks
    """
    path = Path(workflow_path).resolve()

    if not path.exists():
        click.echo(f"Error: workflow file not found: {path}", err=True)
        sys.exit(1)

    try:
        wf, cfg = load_workflow_and_config(path)
    except WorkflowError as e:
        click.echo(f"Error loading workflow: {e}", err=True)
        sys.exit(1)

    err = validate_dispatch_config(cfg)
    if err:
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)

    # CLI --port overrides server.port from workflow front matter.
    effective_port = port if port is not None else cfg.server.port

    try:
        asyncio.run(_run(path, wf, cfg, effective_port))
    except KeyboardInterrupt:
        log.info("shutdown signal=keyboard_interrupt")
    except Exception as e:
        log.error(f"fatal error={e}")
        sys.exit(1)


async def _run(path: Path, wf, cfg, port: Optional[int]) -> None:
    orchestrator = Orchestrator(wf, cfg, path)

    watcher = WorkflowWatcher(
        path=path,
        on_change=orchestrator.reload,
        on_error=orchestrator.on_config_error,
    )
    watcher.start()

    http_runner = None
    if port is not None:
        from .server import start_server
        http_runner = await start_server(orchestrator, port)

    try:
        await orchestrator.start()
        # Keep running until interrupted.
        await asyncio.get_event_loop().create_future()
    finally:
        watcher.stop()
        await orchestrator.stop()
        if http_runner:
            await http_runner.cleanup()
