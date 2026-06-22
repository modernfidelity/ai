"""Core domain model."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


@dataclass
class BlockerRef:
    id: Optional[str]
    identifier: Optional[str]
    state: Optional[str]


@dataclass
class Issue:
    id: str
    identifier: str
    title: str
    description: Optional[str]
    priority: Optional[int]
    state: str
    branch_name: Optional[str]
    url: Optional[str]
    labels: list[str]
    blocked_by: list[BlockerRef]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    def to_template_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "identifier": self.identifier,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "state": self.state,
            "branch_name": self.branch_name,
            "url": self.url,
            "labels": self.labels,
            "blocked_by": [
                {"id": b.id, "identifier": b.identifier, "state": b.state}
                for b in self.blocked_by
            ],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class WorkflowDefinition:
    config: dict[str, Any]
    prompt_template: str


class RunStatus(str, Enum):
    PREPARING_WORKSPACE = "preparing_workspace"
    BUILDING_PROMPT = "building_prompt"
    LAUNCHING_AGENT_PROCESS = "launching_agent_process"
    INITIALIZING_SESSION = "initializing_session"
    STREAMING_TURN = "streaming_turn"
    FINISHING = "finishing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    STALLED = "stalled"
    CANCELED_BY_RECONCILIATION = "canceled_by_reconciliation"


@dataclass
class LiveSession:
    session_id: str
    thread_id: str
    turn_id: str
    codex_app_server_pid: Optional[int] = None
    last_codex_event: Optional[str] = None
    last_codex_timestamp: Optional[datetime] = None
    last_codex_message: Optional[str] = None
    codex_input_tokens: int = 0
    codex_output_tokens: int = 0
    codex_total_tokens: int = 0
    last_reported_input_tokens: int = 0
    last_reported_output_tokens: int = 0
    last_reported_total_tokens: int = 0
    turn_count: int = 0


@dataclass
class RetryEntry:
    issue_id: str
    identifier: str
    attempt: int
    due_at_ms: int  # monotonic ms
    error: Optional[str] = None


@dataclass
class RunningEntry:
    worker_task: asyncio.Task
    identifier: str
    issue: Issue
    session: Optional[LiveSession]
    retry_attempt: Optional[int]
    started_at: datetime
    last_error: Optional[str] = None


@dataclass
class CodexTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    seconds_running: float = 0.0


@dataclass
class OrchestratorState:
    poll_interval_ms: int
    max_concurrent_agents: int
    running: dict[str, RunningEntry] = field(default_factory=dict)
    claimed: set[str] = field(default_factory=set)
    retry_attempts: dict[str, RetryEntry] = field(default_factory=dict)
    retry_timers: dict[str, asyncio.Task] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)
    codex_totals: CodexTotals = field(default_factory=CodexTotals)
    codex_rate_limits: Optional[Any] = None


@dataclass
class Workspace:
    path: str
    workspace_key: str
    created_now: bool


class WorkerOutcome(str, Enum):
    NORMAL = "normal"
    ABNORMAL = "abnormal"


@dataclass
class WorkerResult:
    issue_id: str
    outcome: WorkerOutcome
    error: Optional[str] = None
    runtime_seconds: float = 0.0
    token_delta: Optional[tuple[int, int, int]] = None  # (input, output, total)
