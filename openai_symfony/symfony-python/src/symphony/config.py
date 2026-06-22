"""Configuration resolution pipeline."""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def _resolve_var(value: str) -> Optional[str]:
    """If value is $VAR_NAME, look it up in env. Return None if var is unset/empty."""
    if isinstance(value, str) and re.fullmatch(r'\$[A-Za-z_][A-Za-z0-9_]*', value):
        env_val = os.environ.get(value[1:], "")
        return env_val or None
    return value


def _expand_path(value: str, workflow_dir: Path) -> str:
    expanded = os.path.expanduser(value)
    p = Path(expanded)
    if not p.is_absolute():
        p = workflow_dir / p
    return str(p.resolve())


@dataclass
class TrackerConfig:
    kind: str = "linear"
    endpoint: str = "https://api.linear.app/graphql"
    api_key: Optional[str] = None
    project_slug: Optional[str] = None
    active_states: list[str] = field(default_factory=lambda: ["Todo", "In Progress"])
    terminal_states: list[str] = field(
        default_factory=lambda: ["Closed", "Cancelled", "Canceled", "Duplicate", "Done"]
    )


@dataclass
class PollingConfig:
    interval_ms: int = 30_000


@dataclass
class WorkspaceConfig:
    root: str = ""


@dataclass
class HooksConfig:
    after_create: Optional[str] = None
    before_run: Optional[str] = None
    after_run: Optional[str] = None
    before_remove: Optional[str] = None
    timeout_ms: int = 60_000


@dataclass
class AgentConfig:
    max_concurrent_agents: int = 10
    max_turns: int = 20
    max_retry_backoff_ms: int = 300_000
    max_concurrent_agents_by_state: dict[str, int] = field(default_factory=dict)


@dataclass
class CodexConfig:
    command: str = "codex app-server"
    approval_policy: Optional[str] = None
    thread_sandbox: Optional[str] = None
    turn_sandbox_policy: Optional[str] = None
    turn_timeout_ms: int = 3_600_000
    read_timeout_ms: int = 5_000
    stall_timeout_ms: int = 300_000


@dataclass
class ServerConfig:
    port: Optional[int] = None


@dataclass
class ServiceConfig:
    tracker: TrackerConfig
    polling: PollingConfig
    workspace: WorkspaceConfig
    hooks: HooksConfig
    agent: AgentConfig
    codex: CodexConfig
    server: ServerConfig


class ConfigError(Exception):
    pass


def load_config(raw: dict[str, Any], workflow_path: Path) -> ServiceConfig:
    """Build ServiceConfig from raw YAML front-matter and the workflow file's path."""
    workflow_dir = workflow_path.parent

    # ---- tracker ----
    t = raw.get("tracker") or {}
    api_key_raw = t.get("api_key", "$LINEAR_API_KEY")
    api_key = _resolve_var(str(api_key_raw)) if api_key_raw else _resolve_var("$LINEAR_API_KEY")

    tracker = TrackerConfig(
        kind=t.get("kind", "linear"),
        endpoint=t.get("endpoint", "https://api.linear.app/graphql"),
        api_key=api_key,
        project_slug=t.get("project_slug"),
        active_states=list(t.get("active_states", ["Todo", "In Progress"])),
        terminal_states=list(
            t.get("terminal_states", ["Closed", "Cancelled", "Canceled", "Duplicate", "Done"])
        ),
    )

    # ---- polling ----
    p = raw.get("polling") or {}
    polling = PollingConfig(interval_ms=int(p.get("interval_ms", 30_000)))

    # ---- workspace ----
    w = raw.get("workspace") or {}
    root_raw = w.get("root", "")
    if root_raw:
        resolved_root = _resolve_var(str(root_raw))
        if resolved_root is None:
            resolved_root = ""
        workspace_root = _expand_path(resolved_root, workflow_dir) if resolved_root else ""
    else:
        workspace_root = ""
    if not workspace_root:
        workspace_root = str(Path(tempfile.gettempdir()) / "symphony_workspaces")
    workspace_cfg = WorkspaceConfig(root=workspace_root)

    # ---- hooks ----
    h = raw.get("hooks") or {}
    hooks_timeout = int(h.get("timeout_ms", 60_000))
    if hooks_timeout <= 0:
        raise ConfigError(f"hooks.timeout_ms must be positive, got {hooks_timeout}")
    hooks = HooksConfig(
        after_create=h.get("after_create"),
        before_run=h.get("before_run"),
        after_run=h.get("after_run"),
        before_remove=h.get("before_remove"),
        timeout_ms=hooks_timeout,
    )

    # ---- agent ----
    a = raw.get("agent") or {}
    max_turns = int(a.get("max_turns", 20))
    if max_turns <= 0:
        raise ConfigError(f"agent.max_turns must be positive, got {max_turns}")

    per_state_raw = a.get("max_concurrent_agents_by_state") or {}
    per_state: dict[str, int] = {}
    for k, v in per_state_raw.items():
        try:
            iv = int(v)
            if iv > 0:
                per_state[str(k).lower()] = iv
        except (TypeError, ValueError):
            pass

    agent = AgentConfig(
        max_concurrent_agents=int(a.get("max_concurrent_agents", 10)),
        max_turns=max_turns,
        max_retry_backoff_ms=int(a.get("max_retry_backoff_ms", 300_000)),
        max_concurrent_agents_by_state=per_state,
    )

    # ---- codex ----
    c = raw.get("codex") or {}
    codex = CodexConfig(
        command=str(c.get("command", "codex app-server")),
        approval_policy=c.get("approval_policy"),
        thread_sandbox=c.get("thread_sandbox"),
        turn_sandbox_policy=c.get("turn_sandbox_policy"),
        turn_timeout_ms=int(c.get("turn_timeout_ms", 3_600_000)),
        read_timeout_ms=int(c.get("read_timeout_ms", 5_000)),
        stall_timeout_ms=int(c.get("stall_timeout_ms", 300_000)),
    )

    # ---- server (optional extension) ----
    s = raw.get("server") or {}
    server = ServerConfig(port=s.get("port"))

    return ServiceConfig(
        tracker=tracker,
        polling=polling,
        workspace=workspace_cfg,
        hooks=hooks,
        agent=agent,
        codex=codex,
        server=server,
    )


def validate_dispatch_config(cfg: ServiceConfig) -> Optional[str]:
    """Return an error string if config is invalid for dispatch, else None."""
    if not cfg.tracker.kind:
        return "tracker.kind is missing"
    if cfg.tracker.kind != "linear":
        return f"tracker.kind '{cfg.tracker.kind}' is not supported; only 'linear' is supported"
    if not cfg.tracker.api_key:
        return "tracker.api_key is missing or empty after $VAR resolution"
    if not cfg.tracker.project_slug:
        return "tracker.project_slug is required for tracker.kind=linear"
    if not cfg.codex.command:
        return "codex.command is missing or empty"
    return None
