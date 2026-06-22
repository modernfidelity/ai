"""Section 17.1 — Workflow and Config Parsing."""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from symphony.config import ConfigError, ServiceConfig, load_config, validate_dispatch_config
from symphony.workflow import WorkflowError, load_workflow, load_workflow_and_config, render_prompt

from .conftest import make_issue


# ---------------------------------------------------------------------------
# Workflow loading
# ---------------------------------------------------------------------------

def test_missing_workflow_file(tmp_path: Path) -> None:
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(tmp_path / "WORKFLOW.md")
    assert exc_info.value.code == "missing_workflow_file"


def test_workflow_no_front_matter(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    p.write_text("Hello world\n")
    wf = load_workflow(p)
    assert wf.config == {}
    assert wf.prompt_template == "Hello world"


def test_workflow_with_front_matter(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    p.write_text("---\ntracker:\n  kind: linear\n---\nDo the thing\n")
    wf = load_workflow(p)
    assert wf.config["tracker"]["kind"] == "linear"
    assert wf.prompt_template == "Do the thing"


def test_workflow_invalid_yaml(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    p.write_text("---\n: - bad yaml [\n---\nbody\n")
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(p)
    assert exc_info.value.code == "workflow_parse_error"


def test_workflow_front_matter_not_a_map(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    p.write_text("---\n- item1\n- item2\n---\nbody\n")
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(p)
    assert exc_info.value.code == "workflow_front_matter_not_a_map"


def test_workflow_empty_front_matter(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    p.write_text("---\n---\nsome body\n")
    wf = load_workflow(p)
    assert wf.config == {}
    assert wf.prompt_template == "some body"


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

def test_config_defaults(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    cfg = load_config({}, p)
    assert cfg.polling.interval_ms == 30_000
    assert cfg.agent.max_concurrent_agents == 10
    assert cfg.agent.max_turns == 20
    assert cfg.agent.max_retry_backoff_ms == 300_000
    assert cfg.codex.command == "codex app-server"
    assert cfg.codex.turn_timeout_ms == 3_600_000
    assert cfg.codex.stall_timeout_ms == 300_000
    assert cfg.hooks.timeout_ms == 60_000
    assert "Todo" in cfg.tracker.active_states
    assert "Done" in cfg.tracker.terminal_states


def test_config_tracker_kind(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    cfg = load_config({"tracker": {"kind": "linear"}}, p)
    assert cfg.tracker.kind == "linear"


def test_config_hooks_invalid_timeout(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    with pytest.raises(ConfigError):
        load_config({"hooks": {"timeout_ms": 0}}, p)


def test_config_agent_invalid_max_turns(tmp_path: Path) -> None:
    p = tmp_path / "WORKFLOW.md"
    with pytest.raises(ConfigError):
        load_config({"agent": {"max_turns": -1}}, p)


# ---------------------------------------------------------------------------
# $VAR resolution
# ---------------------------------------------------------------------------

def test_var_resolution_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "tok-abc")
    cfg = load_config({"tracker": {"api_key": "$MY_TOKEN"}}, tmp_path / "WORKFLOW.md")
    assert cfg.tracker.api_key == "tok-abc"


def test_var_resolution_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MY_TOKEN", raising=False)
    cfg = load_config({"tracker": {"api_key": "$MY_TOKEN"}}, tmp_path / "WORKFLOW.md")
    assert cfg.tracker.api_key is None


def test_var_resolution_literal(tmp_path: Path) -> None:
    cfg = load_config({"tracker": {"api_key": "literal-key"}}, tmp_path / "WORKFLOW.md")
    assert cfg.tracker.api_key == "literal-key"


def test_default_linear_api_key_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "env-key")
    cfg = load_config({}, tmp_path / "WORKFLOW.md")
    assert cfg.tracker.api_key == "env-key"


def test_tilde_expansion(tmp_path: Path) -> None:
    cfg = load_config({"workspace": {"root": "~/workspaces"}}, tmp_path / "WORKFLOW.md")
    assert "~" not in cfg.workspace.root
    assert cfg.workspace.root.startswith("/")


def test_relative_workspace_resolved_relative_to_workflow(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    wf_path = sub / "WORKFLOW.md"
    cfg = load_config({"workspace": {"root": "workspaces"}}, wf_path)
    assert cfg.workspace.root == str((sub / "workspaces").resolve())


# ---------------------------------------------------------------------------
# Per-state concurrency
# ---------------------------------------------------------------------------

def test_per_state_concurrency_normalization(tmp_path: Path) -> None:
    cfg = load_config(
        {"agent": {"max_concurrent_agents_by_state": {"In Progress": 3, "Todo": "2"}}},
        tmp_path / "WORKFLOW.md",
    )
    assert cfg.agent.max_concurrent_agents_by_state["in progress"] == 3
    assert cfg.agent.max_concurrent_agents_by_state["todo"] == 2


def test_per_state_concurrency_ignores_invalid(tmp_path: Path) -> None:
    cfg = load_config(
        {"agent": {"max_concurrent_agents_by_state": {"Bad": "notanumber", "Neg": -1}}},
        tmp_path / "WORKFLOW.md",
    )
    assert "bad" not in cfg.agent.max_concurrent_agents_by_state
    assert "neg" not in cfg.agent.max_concurrent_agents_by_state


# ---------------------------------------------------------------------------
# Dispatch validation
# ---------------------------------------------------------------------------

def test_validate_dispatch_config_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "key")
    cfg = load_config(
        {"tracker": {"kind": "linear", "project_slug": "my-proj"}},
        tmp_path / "WORKFLOW.md",
    )
    assert validate_dispatch_config(cfg) is None


def test_validate_dispatch_config_missing_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    cfg = load_config(
        {"tracker": {"kind": "linear", "project_slug": "my-proj"}},
        tmp_path / "WORKFLOW.md",
    )
    err = validate_dispatch_config(cfg)
    assert err is not None
    assert "api_key" in err


def test_validate_dispatch_config_unsupported_kind(tmp_path: Path) -> None:
    cfg = load_config(
        {"tracker": {"kind": "github", "api_key": "k", "project_slug": "p"}},
        tmp_path / "WORKFLOW.md",
    )
    err = validate_dispatch_config(cfg)
    assert err is not None
    assert "linear" in err


def test_validate_dispatch_config_missing_project_slug(tmp_path: Path) -> None:
    cfg = load_config({"tracker": {"kind": "linear", "api_key": "key"}}, tmp_path / "WORKFLOW.md")
    err = validate_dispatch_config(cfg)
    assert err is not None
    assert "project_slug" in err


# ---------------------------------------------------------------------------
# Prompt template rendering (Section 17.1)
# ---------------------------------------------------------------------------

def test_render_prompt_basic(tmp_path: Path) -> None:
    issue = make_issue(identifier="ABC-1", title="Fix bug")
    result = render_prompt("Working on {{ issue.identifier }}: {{ issue.title }}", issue, None)
    assert "ABC-1" in result
    assert "Fix bug" in result


def test_render_prompt_with_attempt(tmp_path: Path) -> None:
    issue = make_issue()
    result = render_prompt(
        "{% if attempt %}Retry {{ attempt }}{% else %}First run{% endif %}", issue, None
    )
    assert "First run" in result

    result2 = render_prompt(
        "{% if attempt %}Retry {{ attempt }}{% else %}First run{% endif %}", issue, 2
    )
    assert "Retry 2" in result2


def test_render_prompt_unknown_variable_fails() -> None:
    issue = make_issue()
    with pytest.raises(WorkflowError) as exc_info:
        render_prompt("{{ issue.nonexistent_field }}", issue, None)
    assert exc_info.value.code == "template_render_error"


def test_render_prompt_empty_uses_fallback() -> None:
    issue = make_issue()
    result = render_prompt("", issue, None)
    assert "Linear" in result


def test_render_prompt_labels_iterable() -> None:
    issue = make_issue(labels=["bug", "critical"])
    result = render_prompt(
        "{% for l in issue.labels %}{{ l }} {% endfor %}", issue, None
    )
    assert "bug" in result
    assert "critical" in result
