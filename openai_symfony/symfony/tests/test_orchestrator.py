"""Section 17.4 — Orchestrator Dispatch, Reconciliation, and Retry."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from symphony.agent import _is_active
from symphony.config import AgentConfig, ServiceConfig, TrackerConfig, load_config
from symphony.models import BlockerRef, OrchestratorState, RunningEntry, RetryEntry
from symphony.orchestrator import (
    Orchestrator,
    _all_blockers_terminal,
    _backoff_ms,
    _sort_key,
)
from symphony.workflow import load_workflow_and_config

from .conftest import make_issue


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Dispatch sort order (spec §8.2)
# ---------------------------------------------------------------------------

def test_sort_priority_ascending() -> None:
    i1 = make_issue(id="1", priority=3, created_at=_dt("2025-01-01"))
    i2 = make_issue(id="2", priority=1, created_at=_dt("2025-01-02"))
    sorted_issues = sorted([i1, i2], key=_sort_key)
    assert sorted_issues[0].id == "2"  # priority 1 first


def test_sort_null_priority_last() -> None:
    i1 = make_issue(id="1", priority=None, created_at=_dt("2025-01-01"))
    i2 = make_issue(id="2", priority=2, created_at=_dt("2025-01-02"))
    sorted_issues = sorted([i1, i2], key=_sort_key)
    assert sorted_issues[0].id == "2"  # priority 2 before None


def test_sort_oldest_first_same_priority() -> None:
    i1 = make_issue(id="1", priority=1, created_at=_dt("2025-01-02"))
    i2 = make_issue(id="2", priority=1, created_at=_dt("2025-01-01"))
    sorted_issues = sorted([i1, i2], key=_sort_key)
    assert sorted_issues[0].id == "2"  # older first


def test_sort_identifier_tiebreaker() -> None:
    i1 = make_issue(id="1", identifier="ABC-2", priority=1, created_at=_dt("2025-01-01"))
    i2 = make_issue(id="2", identifier="ABC-1", priority=1, created_at=_dt("2025-01-01"))
    sorted_issues = sorted([i1, i2], key=_sort_key)
    assert sorted_issues[0].identifier == "ABC-1"


# ---------------------------------------------------------------------------
# Blocker rules (spec §8.2)
# ---------------------------------------------------------------------------

def test_todo_with_non_terminal_blocker_not_eligible() -> None:
    terminal_states = ["Done", "Cancelled"]
    blocker = BlockerRef(id="b1", identifier="ABC-0", state="In Progress")
    issue = make_issue(state="Todo", blocked_by=[blocker])
    assert not _all_blockers_terminal(issue, terminal_states)


def test_todo_with_terminal_blockers_is_eligible() -> None:
    terminal_states = ["Done", "Cancelled"]
    blocker = BlockerRef(id="b1", identifier="ABC-0", state="Done")
    issue = make_issue(state="Todo", blocked_by=[blocker])
    assert _all_blockers_terminal(issue, terminal_states)


def test_todo_no_blockers_is_eligible() -> None:
    assert _all_blockers_terminal(make_issue(state="Todo", blocked_by=[]), ["Done"])


# ---------------------------------------------------------------------------
# Retry backoff (spec §8.4)
# ---------------------------------------------------------------------------

def test_backoff_first_retry() -> None:
    assert _backoff_ms(1, 300_000) == 10_000


def test_backoff_second_retry() -> None:
    assert _backoff_ms(2, 300_000) == 20_000


def test_backoff_capped_at_max() -> None:
    # 2^10 * 10000 = 10240000 >> 300000
    assert _backoff_ms(10, 300_000) == 300_000


def test_backoff_custom_max() -> None:
    assert _backoff_ms(5, 60_000) == 60_000


# ---------------------------------------------------------------------------
# Orchestrator: should_dispatch
# ---------------------------------------------------------------------------

def _make_orchestrator(tmp_path: Path, api_key: str = "key") -> Orchestrator:
    """Create orchestrator with a minimal config."""
    raw = {
        "tracker": {
            "kind": "linear",
            "api_key": api_key,
            "project_slug": "proj",
        }
    }
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("---\ntracker:\n  kind: linear\n  api_key: key\n  project_slug: proj\n---\nDo it\n")
    from symphony.workflow import load_workflow_and_config
    wf, cfg = load_workflow_and_config(wf_path)
    return Orchestrator(wf, cfg, wf_path)


def test_should_dispatch_basic(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    issue = make_issue(state="In Progress")
    assert orch._should_dispatch(issue)


def test_should_dispatch_already_running(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    issue = make_issue(state="In Progress")
    # Pretend it's running.
    orch._state.running[issue.id] = MagicMock()
    assert not orch._should_dispatch(issue)


def test_should_dispatch_already_claimed(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    issue = make_issue(state="In Progress")
    orch._state.claimed.add(issue.id)
    assert not orch._should_dispatch(issue)


def test_should_dispatch_terminal_state(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    issue = make_issue(state="Done")
    assert not orch._should_dispatch(issue)


def test_should_dispatch_inactive_state(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    issue = make_issue(state="Backlog")  # not in active_states
    assert not orch._should_dispatch(issue)


def test_should_dispatch_no_slots(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    orch._state.max_concurrent_agents = 1
    # Fill the one slot.
    orch._state.running["other-id"] = MagicMock()
    issue = make_issue(state="In Progress")
    assert not orch._should_dispatch(issue)


def test_should_dispatch_todo_non_terminal_blocker(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    blocker = BlockerRef(id="b1", identifier="ABC-0", state="In Progress")
    issue = make_issue(state="Todo", blocked_by=[blocker])
    assert not orch._should_dispatch(issue)


def test_should_dispatch_todo_terminal_blocker(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    blocker = BlockerRef(id="b1", identifier="ABC-0", state="Done")
    issue = make_issue(state="Todo", blocked_by=[blocker])
    assert orch._should_dispatch(issue)


# ---------------------------------------------------------------------------
# Orchestrator: snapshot
# ---------------------------------------------------------------------------

def test_snapshot_structure(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    snap = orch.snapshot()
    assert "running" in snap
    assert "retrying" in snap
    assert "codex_totals" in snap
    assert "counts" in snap
    assert snap["counts"]["running"] == 0
    assert snap["counts"]["retrying"] == 0


# ---------------------------------------------------------------------------
# _is_active helper
# ---------------------------------------------------------------------------

def test_is_active_case_insensitive() -> None:
    assert _is_active("in progress", ["In Progress", "Todo"])
    assert _is_active("IN PROGRESS", ["In Progress"])
    assert not _is_active("Done", ["In Progress", "Todo"])


# ---------------------------------------------------------------------------
# Reload (hot config update)
# ---------------------------------------------------------------------------

def test_reload_updates_poll_interval(tmp_path: Path) -> None:
    orch = _make_orchestrator(tmp_path)
    assert orch._state.poll_interval_ms == 30_000

    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text(
        "---\ntracker:\n  kind: linear\n  api_key: key\n  project_slug: proj\n"
        "polling:\n  interval_ms: 5000\n---\nDo it\n"
    )
    wf, cfg = load_workflow_and_config(wf_path)
    orch.reload(wf, cfg)
    assert orch._state.poll_interval_ms == 5_000
