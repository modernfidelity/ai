"""Shared test fixtures."""
from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from symphony.models import BlockerRef, Issue


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def make_issue(
    id: str = "issue-1",
    identifier: str = "ABC-1",
    title: str = "Test issue",
    state: str = "In Progress",
    priority: int | None = None,
    blocked_by: list | None = None,
    labels: list[str] | None = None,
    created_at: datetime | None = None,
) -> Issue:
    return Issue(
        id=id,
        identifier=identifier,
        title=title,
        description="A test issue",
        priority=priority,
        state=state,
        branch_name=None,
        url=None,
        labels=labels or [],
        blocked_by=blocked_by or [],
        created_at=created_at or _dt("2025-01-01T00:00:00"),
        updated_at=None,
    )


@pytest.fixture
def simple_workflow_file(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
        ---
        tracker:
          kind: linear
          api_key: $LINEAR_API_KEY
          project_slug: my-project
        ---
        You are working on {{ issue.identifier }}: {{ issue.title }}.
    """)
    p = tmp_path / "WORKFLOW.md"
    p.write_text(content)
    return p


@pytest.fixture
def minimal_workflow_file(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
        ---
        tracker:
          kind: linear
          api_key: test-key
          project_slug: my-project
        ---
        Issue: {{ issue.identifier }}
    """)
    p = tmp_path / "WORKFLOW.md"
    p.write_text(content)
    return p
