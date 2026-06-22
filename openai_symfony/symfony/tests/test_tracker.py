"""Section 17.3 — Issue Tracker Client."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from symphony.config import TrackerConfig
from symphony.tracker.linear import LinearClient, TrackerError, _node_to_issue, _node_to_minimal_issue
from symphony.models import BlockerRef


def make_cfg(**kwargs) -> TrackerConfig:
    defaults = dict(
        kind="linear",
        endpoint="https://api.linear.app/graphql",
        api_key="test-key",
        project_slug="my-project",
    )
    defaults.update(kwargs)
    return TrackerConfig(**defaults)


def _issue_node(
    id: str = "i1",
    identifier: str = "ABC-1",
    title: str = "Fix bug",
    state: str = "In Progress",
    priority: int | None = 2,
    labels: list[str] | None = None,
    inverse_relations: list | None = None,
) -> dict:
    return {
        "id": id,
        "identifier": identifier,
        "title": title,
        "description": "desc",
        "priority": priority,
        "branchName": None,
        "url": None,
        "createdAt": "2025-01-01T00:00:00.000Z",
        "updatedAt": "2025-01-02T00:00:00.000Z",
        "state": {"name": state},
        "labels": {"nodes": [{"name": l} for l in (labels or [])]},
        "inverseRelations": {"nodes": inverse_relations or []},
    }


# ---------------------------------------------------------------------------
# Node normalization
# ---------------------------------------------------------------------------

def test_node_to_issue_basic() -> None:
    node = _issue_node()
    issue = _node_to_issue(node)
    assert issue.id == "i1"
    assert issue.identifier == "ABC-1"
    assert issue.title == "Fix bug"
    assert issue.state == "In Progress"
    assert issue.priority == 2


def test_node_labels_normalized_to_lowercase() -> None:
    node = _issue_node(labels=["BUG", "Critical", "backend"])
    issue = _node_to_issue(node)
    assert issue.labels == ["bug", "critical", "backend"]


def test_node_priority_non_integer_becomes_none() -> None:
    node = _issue_node()
    node["priority"] = "high"
    issue = _node_to_issue(node)
    assert issue.priority is None


def test_node_blocked_by_from_inverse_relations() -> None:
    relation = {
        "relatedIssue": {
            "id": "blocker-id",
            "identifier": "ABC-0",
            "state": {"name": "Done"},
        }
    }
    node = _issue_node(inverse_relations=[relation])
    issue = _node_to_issue(node)
    assert len(issue.blocked_by) == 1
    assert issue.blocked_by[0].id == "blocker-id"
    assert issue.blocked_by[0].identifier == "ABC-0"
    assert issue.blocked_by[0].state == "Done"


def test_node_timestamps_parsed() -> None:
    node = _issue_node()
    issue = _node_to_issue(node)
    assert issue.created_at is not None
    assert issue.updated_at is not None


# ---------------------------------------------------------------------------
# Error handling (without real HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_api_key_raises() -> None:
    cfg = make_cfg(api_key=None)
    client = LinearClient(cfg)
    with pytest.raises(TrackerError) as exc_info:
        await client.fetch_candidate_issues()
    assert exc_info.value.code == "missing_tracker_api_key"
    await client.close()


@pytest.mark.asyncio
async def test_missing_project_slug_raises() -> None:
    cfg = make_cfg(project_slug=None)
    client = LinearClient(cfg)
    with pytest.raises(TrackerError) as exc_info:
        await client.fetch_candidate_issues()
    assert exc_info.value.code == "missing_tracker_project_slug"
    await client.close()


@pytest.mark.asyncio
async def test_fetch_issues_by_states_empty_returns_empty() -> None:
    cfg = make_cfg()
    client = LinearClient(cfg)
    result = await client.fetch_issues_by_states([])
    assert result == []
    await client.close()


@pytest.mark.asyncio
async def test_fetch_issue_states_by_ids_empty_returns_empty() -> None:
    cfg = make_cfg()
    client = LinearClient(cfg)
    result = await client.fetch_issue_states_by_ids([])
    assert result == []
    await client.close()


# ---------------------------------------------------------------------------
# Mocked GraphQL responses
# ---------------------------------------------------------------------------

def _mock_graphql_response(data: dict) -> Any:
    """Return a mock that simulates a successful aiohttp response."""
    resp = AsyncMock()
    resp.status = 200
    resp.json = AsyncMock(return_value={"data": data})
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_fetch_candidate_issues_single_page() -> None:
    cfg = make_cfg()
    client = LinearClient(cfg)

    mock_data = {
        "issues": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [_issue_node("id1", "ABC-1"), _issue_node("id2", "ABC-2")],
        }
    }

    with patch.object(client, "_graphql", new=AsyncMock(return_value=mock_data["data"] if False else mock_data)):
        # Patch _graphql directly since it's easier to mock at that level.
        async def fake_graphql(query, variables):
            return {
                "issues": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [_issue_node("id1", "ABC-1"), _issue_node("id2", "ABC-2")],
                }
            }
        client._graphql = fake_graphql  # type: ignore[method-assign]
        issues = await client.fetch_candidate_issues()

    assert len(issues) == 2
    assert issues[0].identifier == "ABC-1"
    assert issues[1].identifier == "ABC-2"
    await client.close()


@pytest.mark.asyncio
async def test_fetch_candidate_issues_pagination() -> None:
    cfg = make_cfg()
    client = LinearClient(cfg)

    calls = []

    async def fake_graphql(query, variables):
        calls.append(variables.get("after"))
        if variables.get("after") is None:
            return {
                "issues": {
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                    "nodes": [_issue_node("id1", "ABC-1")],
                }
            }
        return {
            "issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [_issue_node("id2", "ABC-2")],
            }
        }

    client._graphql = fake_graphql  # type: ignore[method-assign]
    issues = await client.fetch_candidate_issues()

    assert len(issues) == 2
    assert calls == [None, "cursor1"]
    await client.close()


@pytest.mark.asyncio
async def test_graphql_errors_raises() -> None:
    cfg = make_cfg()
    client = LinearClient(cfg)

    async def fake_graphql(query, variables):
        from symphony.tracker.linear import TrackerError as TE
        raise TE("linear_graphql_errors", "Something went wrong")

    client._graphql = fake_graphql  # type: ignore[method-assign]
    with pytest.raises(TrackerError) as exc_info:
        await client.fetch_candidate_issues()
    assert exc_info.value.code == "linear_graphql_errors"
    await client.close()


@pytest.mark.asyncio
async def test_fetch_issue_states_by_ids_uses_id_list() -> None:
    cfg = make_cfg()
    client = LinearClient(cfg)

    received_vars = {}

    async def fake_graphql(query, variables):
        received_vars.update(variables)
        return {
            "issues": {
                "nodes": [
                    {"id": "id1", "identifier": "ABC-1", "state": {"name": "Done"}},
                ]
            }
        }

    client._graphql = fake_graphql  # type: ignore[method-assign]
    result = await client.fetch_issue_states_by_ids(["id1", "id2"])

    assert "ids" in received_vars
    assert set(received_vars["ids"]) == {"id1", "id2"}
    assert len(result) == 1
    assert result[0].state == "Done"
    await client.close()
