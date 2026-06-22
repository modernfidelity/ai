"""Linear GraphQL tracker adapter."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from ..config import TrackerConfig
from ..models import BlockerRef, Issue


class TrackerError(Exception):
    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_CANDIDATE_QUERY = """
query CandidateIssues($projectSlug: String!, $states: [String!]!, $after: String) {
  issues(
    filter: {
      project: { slugId: { eq: $projectSlug } }
      state: { name: { in: $states } }
    }
    first: 50
    after: $after
    orderBy: createdAt
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      identifier
      title
      description
      priority
      branchName
      url
      createdAt
      updatedAt
      state {
        name
      }
      labels {
        nodes {
          name
        }
      }
      inverseRelations(filter: { type: { eq: "blocks" } }) {
        nodes {
          relatedIssue {
            id
            identifier
            state {
              name
            }
          }
        }
      }
    }
  }
}
"""

_ISSUES_BY_STATES_QUERY = """
query IssuesByStates($states: [String!]!, $after: String) {
  issues(
    filter: {
      state: { name: { in: $states } }
    }
    first: 50
    after: $after
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      identifier
      state {
        name
      }
    }
  }
}
"""

_ISSUES_BY_IDS_QUERY = """
query IssuesByIds($ids: [ID!]!) {
  issues(filter: { id: { in: $ids } }) {
    nodes {
      id
      identifier
      state {
        name
      }
    }
  }
}
"""


def _parse_priority(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _node_to_issue(node: dict[str, Any]) -> Issue:
    state_name = (node.get("state") or {}).get("name", "")
    labels = [
        lbl["name"].lower()
        for lbl in (node.get("labels") or {}).get("nodes", [])
        if lbl.get("name")
    ]
    blockers: list[BlockerRef] = []
    for rel in (node.get("inverseRelations") or {}).get("nodes", []):
        ri = rel.get("relatedIssue") or {}
        blockers.append(
            BlockerRef(
                id=ri.get("id"),
                identifier=ri.get("identifier"),
                state=(ri.get("state") or {}).get("name"),
            )
        )
    return Issue(
        id=node["id"],
        identifier=node["identifier"],
        title=node.get("title", ""),
        description=node.get("description"),
        priority=_parse_priority(node.get("priority")),
        state=state_name,
        branch_name=node.get("branchName"),
        url=node.get("url"),
        labels=labels,
        blocked_by=blockers,
        created_at=_parse_dt(node.get("createdAt")),
        updated_at=_parse_dt(node.get("updatedAt")),
    )


def _node_to_minimal_issue(node: dict[str, Any]) -> Issue:
    """Minimal issue with only id, identifier, state for reconciliation."""
    state_name = (node.get("state") or {}).get("name", "")
    return Issue(
        id=node["id"],
        identifier=node.get("identifier", ""),
        title="",
        description=None,
        priority=None,
        state=state_name,
        branch_name=None,
        url=None,
        labels=[],
        blocked_by=[],
        created_at=None,
        updated_at=None,
    )


class LinearClient:
    """Async Linear GraphQL client."""

    TIMEOUT_SECONDS = 30

    def __init__(self, cfg: TrackerConfig) -> None:
        self._cfg = cfg
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": self._cfg.api_key or "",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=self.TIMEOUT_SECONDS),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if not self._cfg.api_key:
            raise TrackerError("missing_tracker_api_key", "tracker.api_key is not configured")
        session = self._get_session()
        try:
            async with session.post(
                self._cfg.endpoint,
                json={"query": query, "variables": variables},
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise TrackerError(
                        "linear_api_status",
                        f"Linear API returned HTTP {resp.status}: {text[:200]}",
                    )
                payload = await resp.json()
        except aiohttp.ClientError as e:
            raise TrackerError("linear_api_request", f"Linear API request failed: {e}") from e

        if not isinstance(payload, dict):
            raise TrackerError("linear_unknown_payload", "Unexpected non-dict response from Linear")

        if "errors" in payload and payload["errors"]:
            msgs = "; ".join(e.get("message", str(e)) for e in payload["errors"])
            raise TrackerError("linear_graphql_errors", f"GraphQL errors: {msgs}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise TrackerError("linear_unknown_payload", "No 'data' key in Linear response")

        return data

    async def fetch_candidate_issues(self) -> list[Issue]:
        """Fetch all issues in active states for the configured project."""
        if not self._cfg.project_slug:
            raise TrackerError(
                "missing_tracker_project_slug", "tracker.project_slug is not configured"
            )

        issues: list[Issue] = []
        cursor: Optional[str] = None

        while True:
            data = await self._graphql(
                _CANDIDATE_QUERY,
                {
                    "projectSlug": self._cfg.project_slug,
                    "states": self._cfg.active_states,
                    "after": cursor,
                },
            )
            result = data.get("issues") or {}
            nodes = result.get("nodes") or []
            for node in nodes:
                try:
                    issues.append(_node_to_issue(node))
                except (KeyError, TypeError):
                    pass  # skip malformed nodes

            page_info = result.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if cursor is None:
                raise TrackerError(
                    "linear_missing_end_cursor",
                    "Pagination error: hasNextPage=true but endCursor is null",
                )

        return issues

    async def fetch_issues_by_states(self, state_names: list[str]) -> list[Issue]:
        """Fetch issues in specific states (used for startup terminal cleanup)."""
        if not state_names:
            return []

        issues: list[Issue] = []
        cursor: Optional[str] = None

        while True:
            data = await self._graphql(
                _ISSUES_BY_STATES_QUERY,
                {"states": state_names, "after": cursor},
            )
            result = data.get("issues") or {}
            nodes = result.get("nodes") or []
            for node in nodes:
                try:
                    issues.append(_node_to_minimal_issue(node))
                except (KeyError, TypeError):
                    pass

            page_info = result.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if cursor is None:
                raise TrackerError(
                    "linear_missing_end_cursor",
                    "Pagination error: hasNextPage=true but endCursor is null",
                )

        return issues

    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        """Fetch current states for specific issue IDs (used for reconciliation)."""
        if not issue_ids:
            return []
        data = await self._graphql(_ISSUES_BY_IDS_QUERY, {"ids": issue_ids})
        result = data.get("issues") or {}
        nodes = result.get("nodes") or []
        out: list[Issue] = []
        for node in nodes:
            try:
                out.append(_node_to_minimal_issue(node))
            except (KeyError, TypeError):
                pass
        return out
