"""Workspace management and lifecycle hooks."""
from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Optional

from . import log
from .config import HooksConfig, WorkspaceConfig
from .models import Workspace

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_identifier(identifier: str) -> str:
    return _SAFE_CHARS.sub("_", identifier)


class WorkspaceError(Exception):
    pass


class WorkspaceManager:
    def __init__(self, cfg: WorkspaceConfig, hooks: HooksConfig) -> None:
        self._cfg = cfg
        self._hooks = hooks

    @property
    def root(self) -> Path:
        return Path(self._cfg.root)

    def workspace_path(self, identifier: str) -> Path:
        key = sanitize_identifier(identifier)
        path = self.root / key
        # Safety: path must be inside root
        root_resolved = self.root.resolve()
        path_resolved = path.resolve()
        try:
            path_resolved.relative_to(root_resolved)
        except ValueError:
            raise WorkspaceError(
                f"Workspace path {path_resolved} escapes workspace root {root_resolved}"
            )
        return path_resolved

    async def create_for_issue(self, identifier: str) -> Workspace:
        """Ensure workspace directory exists, run after_create hook if new."""
        key = sanitize_identifier(identifier)
        path = self.workspace_path(identifier)
        root = self.root

        root.mkdir(parents=True, exist_ok=True)

        created_now = False
        if path.exists():
            if not path.is_dir():
                raise WorkspaceError(f"Workspace path {path} exists but is not a directory")
        else:
            path.mkdir(parents=True)
            created_now = True

        ws = Workspace(path=str(path), workspace_key=key, created_now=created_now)

        if created_now and self._hooks.after_create:
            log.info(
                "hook=after_create status=start",
                workspace=str(path),
                identifier=identifier,
            )
            try:
                await self._run_hook(self._hooks.after_create, path, "after_create")
            except WorkspaceError:
                shutil.rmtree(str(path), ignore_errors=True)
                raise

        return ws

    async def remove_workspace(self, identifier: str) -> None:
        """Remove workspace for a terminal issue, running before_remove hook first."""
        path = self.workspace_path(identifier)
        if not path.exists():
            return

        if self._hooks.before_remove:
            log.info("hook=before_remove status=start", workspace=str(path))
            try:
                await self._run_hook(self._hooks.before_remove, path, "before_remove")
            except WorkspaceError as e:
                log.warn(f"hook=before_remove status=failed error={e}", workspace=str(path))
            # failure is logged and ignored; cleanup still proceeds

        shutil.rmtree(str(path), ignore_errors=True)
        log.info("workspace status=removed", workspace=str(path))

    async def run_before_run(self, path: Path, identifier: str) -> None:
        if not self._hooks.before_run:
            return
        log.info("hook=before_run status=start", workspace=str(path), identifier=identifier)
        await self._run_hook(self._hooks.before_run, path, "before_run")

    async def run_after_run(self, path: Path, identifier: str) -> None:
        if not self._hooks.after_run:
            return
        log.info("hook=after_run status=start", workspace=str(path), identifier=identifier)
        try:
            await self._run_hook(self._hooks.after_run, path, "after_run")
        except WorkspaceError as e:
            log.warn(f"hook=after_run status=failed error={e}", workspace=str(path))
        # failure logged and ignored

    async def _run_hook(self, script: str, cwd: Path, hook_name: str) -> None:
        timeout_s = self._hooks.timeout_ms / 1000
        try:
            proc = await asyncio.create_subprocess_shell(
                f"bash -lc {_shell_quote(script)}",
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise WorkspaceError(f"Hook {hook_name} timed out after {self._hooks.timeout_ms}ms")
        except OSError as e:
            raise WorkspaceError(f"Hook {hook_name} failed to start: {e}") from e

        if proc.returncode != 0:
            stderr_preview = (stderr or b"")[:500].decode(errors="replace")
            raise WorkspaceError(
                f"Hook {hook_name} exited with code {proc.returncode}: {stderr_preview}"
            )


def _shell_quote(s: str) -> str:
    """Wrap a script string in single quotes, escaping embedded single quotes."""
    return "'" + s.replace("'", "'\\''") + "'"
