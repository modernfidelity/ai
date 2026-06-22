"""Section 17.2 — Workspace Manager and Safety."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from symphony.config import HooksConfig, WorkspaceConfig
from symphony.workspace import WorkspaceError, WorkspaceManager, sanitize_identifier


def make_wm(tmp_path: Path, hooks: HooksConfig | None = None) -> WorkspaceManager:
    cfg = WorkspaceConfig(root=str(tmp_path / "workspaces"))
    return WorkspaceManager(cfg, hooks or HooksConfig())


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

def test_sanitize_identifier_allows_safe_chars() -> None:
    assert sanitize_identifier("ABC-123") == "ABC-123"
    assert sanitize_identifier("my.issue_1") == "my.issue_1"


def test_sanitize_identifier_replaces_unsafe() -> None:
    assert sanitize_identifier("ABC/123") == "ABC_123"
    assert sanitize_identifier("my issue") == "my_issue"
    assert sanitize_identifier("a:b@c!d") == "a_b_c_d"


# ---------------------------------------------------------------------------
# Workspace creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_creates_new_workspace(tmp_path: Path) -> None:
    wm = make_wm(tmp_path)
    ws = await wm.create_for_issue("ABC-1")
    assert ws.created_now is True
    assert Path(ws.path).is_dir()
    assert ws.workspace_key == "ABC-1"


@pytest.mark.asyncio
async def test_reuses_existing_workspace(tmp_path: Path) -> None:
    wm = make_wm(tmp_path)
    ws1 = await wm.create_for_issue("ABC-1")
    ws2 = await wm.create_for_issue("ABC-1")
    assert ws1.path == ws2.path
    assert ws2.created_now is False


@pytest.mark.asyncio
async def test_deterministic_path(tmp_path: Path) -> None:
    wm = make_wm(tmp_path)
    ws1 = await wm.create_for_issue("ABC-1")
    ws2 = await wm.create_for_issue("ABC-1")
    assert ws1.path == ws2.path


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------

def test_workspace_path_inside_root(tmp_path: Path) -> None:
    wm = make_wm(tmp_path)
    wm.root.mkdir(parents=True, exist_ok=True)
    path = wm.workspace_path("ABC-1")
    root = wm.root.resolve()
    assert str(path).startswith(str(root))


def test_workspace_path_cannot_escape_root(tmp_path: Path) -> None:
    wm = make_wm(tmp_path)
    wm.root.mkdir(parents=True, exist_ok=True)
    # After sanitization "../../etc" becomes ".._.._etc" which is safe.
    safe_key = sanitize_identifier("../../etc")
    assert "/" not in safe_key


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_after_create_runs_on_new(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    hooks = HooksConfig(after_create=f"touch {marker}")
    wm = make_wm(tmp_path, hooks)
    ws = await wm.create_for_issue("ABC-1")
    assert marker.exists()
    assert ws.created_now is True


@pytest.mark.asyncio
async def test_after_create_does_not_run_on_reuse(tmp_path: Path) -> None:
    counter_file = tmp_path / "count.txt"
    counter_file.write_text("0")
    hooks = HooksConfig(
        after_create=f"echo $(($(cat {counter_file}) + 1)) > {counter_file}"
    )
    wm = make_wm(tmp_path, hooks)
    await wm.create_for_issue("ABC-1")
    await wm.create_for_issue("ABC-1")
    # Hook runs only once (on creation).
    assert counter_file.read_text().strip() == "1"


@pytest.mark.asyncio
async def test_after_create_failure_aborts_and_cleans(tmp_path: Path) -> None:
    hooks = HooksConfig(after_create="exit 1")
    wm = make_wm(tmp_path, hooks)
    with pytest.raises(WorkspaceError):
        await wm.create_for_issue("ABC-1")
    # Workspace should be removed on failure.
    ws_path = wm.root / "ABC-1"
    assert not ws_path.exists()


@pytest.mark.asyncio
async def test_before_run_failure_aborts(tmp_path: Path) -> None:
    hooks = HooksConfig(before_run="exit 1")
    wm = make_wm(tmp_path, hooks)
    ws = await wm.create_for_issue("ABC-2")
    with pytest.raises(WorkspaceError):
        await wm.run_before_run(Path(ws.path), "ABC-2")


@pytest.mark.asyncio
async def test_after_run_failure_ignored(tmp_path: Path) -> None:
    hooks = HooksConfig(after_run="exit 1")
    wm = make_wm(tmp_path, hooks)
    ws = await wm.create_for_issue("ABC-3")
    # Should not raise.
    await wm.run_after_run(Path(ws.path), "ABC-3")


@pytest.mark.asyncio
async def test_hook_timeout(tmp_path: Path) -> None:
    hooks = HooksConfig(after_create="sleep 10", timeout_ms=100)
    wm = make_wm(tmp_path, hooks)
    with pytest.raises(WorkspaceError, match="timed out"):
        await wm.create_for_issue("ABC-1")


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_workspace(tmp_path: Path) -> None:
    wm = make_wm(tmp_path)
    await wm.create_for_issue("ABC-1")
    await wm.remove_workspace("ABC-1")
    assert not (wm.root / "ABC-1").exists()


@pytest.mark.asyncio
async def test_remove_nonexistent_workspace_is_noop(tmp_path: Path) -> None:
    wm = make_wm(tmp_path)
    # Should not raise.
    await wm.remove_workspace("NONEXISTENT-99")


@pytest.mark.asyncio
async def test_before_remove_failure_ignored(tmp_path: Path) -> None:
    hooks = HooksConfig(before_remove="exit 1")
    wm = make_wm(tmp_path, hooks)
    await wm.create_for_issue("ABC-4")
    # Should not raise; cleanup still proceeds.
    await wm.remove_workspace("ABC-4")
    assert not (wm.root / "ABC-4").exists()
