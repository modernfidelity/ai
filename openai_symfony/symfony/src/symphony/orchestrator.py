"""Central orchestrator: poll loop, dispatch, reconciliation, retry."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import log
from .agent import AgentRunner, _is_active
from .config import ServiceConfig, validate_dispatch_config
from .models import (
    CodexTotals,
    Issue,
    LiveSession,
    OrchestratorState,
    RetryEntry,
    RunningEntry,
    WorkerOutcome,
    WorkerResult,
)
from .tracker.linear import LinearClient, TrackerError
from .workflow import WorkflowDefinition
from .workspace import WorkspaceManager


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mono_ms() -> int:
    return int(time.monotonic() * 1000)


_CONTINUATION_DELAY_MS = 1_000


def _backoff_ms(attempt: int, max_ms: int) -> int:
    raw = 10_000 * (2 ** (attempt - 1))
    return min(raw, max_ms)


def _normalize_attempt(attempt: Optional[int]) -> Optional[int]:
    return attempt  # first run = None; retries = 1+


def _is_terminal(state: str, terminal_states: list[str]) -> bool:
    return state.lower() in [s.lower() for s in terminal_states]


def _sort_key(issue: Issue) -> tuple:
    prio = issue.priority if issue.priority is not None else 9999
    created = issue.created_at or datetime.min.replace(tzinfo=timezone.utc)
    return (prio, created, issue.identifier)


def _all_blockers_terminal(issue: Issue, terminal_states: list[str]) -> bool:
    for b in issue.blocked_by:
        if b.state is None or not _is_terminal(b.state, terminal_states):
            return False
    return True


class Orchestrator:
    """Single-authority orchestrator that owns all scheduling state."""

    def __init__(
        self,
        workflow: WorkflowDefinition,
        cfg: ServiceConfig,
        workflow_path: Any,
    ) -> None:
        self._workflow = workflow
        self._cfg = cfg
        self._workflow_path = workflow_path
        self._state = OrchestratorState(
            poll_interval_ms=cfg.polling.interval_ms,
            max_concurrent_agents=cfg.agent.max_concurrent_agents,
        )
        self._tracker: Optional[LinearClient] = None
        self._workspace_manager: Optional[WorkspaceManager] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._observers: list[Callable[[], None]] = []
        self._last_config_error: Optional[str] = None

    def add_observer(self, fn: Callable[[], None]) -> None:
        self._observers.append(fn)

    def _notify(self) -> None:
        for fn in self._observers:
            try:
                fn()
            except Exception:
                pass

    def reload(self, workflow: WorkflowDefinition, cfg: ServiceConfig) -> None:
        """Apply a reloaded WORKFLOW.md without restart."""
        log.info("workflow reload=applied")
        self._workflow = workflow
        self._cfg = cfg
        self._state.poll_interval_ms = cfg.polling.interval_ms
        self._state.max_concurrent_agents = cfg.agent.max_concurrent_agents
        if self._tracker:
            self._tracker._cfg = cfg.tracker
        if self._workspace_manager:
            self._workspace_manager._cfg = cfg.workspace
            self._workspace_manager._hooks = cfg.hooks
        self._last_config_error = None
        self._notify()

    def on_config_error(self, err: Any) -> None:
        msg = str(err)
        log.error(f"workflow reload=invalid error={msg}")
        self._last_config_error = msg
        self._notify()

    async def start(self) -> None:
        """Start orchestrator: validate, startup cleanup, schedule first tick."""
        self._tracker = LinearClient(self._cfg.tracker)
        self._workspace_manager = WorkspaceManager(self._cfg.workspace, self._cfg.hooks)

        err = validate_dispatch_config(self._cfg)
        if err:
            log.error(f"startup validation=failed error={err}")
            raise RuntimeError(f"Startup validation failed: {err}")

        await self._startup_terminal_cleanup()
        self._schedule_tick(delay_ms=0)

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
        for entry in list(self._state.running.values()):
            entry.worker_task.cancel()
        for task in list(self._state.retry_timers.values()):
            task.cancel()
        if self._tracker:
            await self._tracker.close()

    def snapshot(self) -> dict[str, Any]:
        """Return a synchronous runtime snapshot for the status surface."""
        now = _now()
        running_rows = []
        for issue_id, entry in self._state.running.items():
            sess = entry.session
            running_rows.append({
                "issue_id": issue_id,
                "issue_identifier": entry.identifier,
                "state": entry.issue.state,
                "session_id": sess.session_id if sess else None,
                "turn_count": sess.turn_count if sess else 0,
                "last_event": sess.last_codex_event if sess else None,
                "last_message": sess.last_codex_message if sess else None,
                "started_at": entry.started_at.isoformat(),
                "last_event_at": sess.last_codex_timestamp.isoformat() if sess and sess.last_codex_timestamp else None,
                "tokens": {
                    "input_tokens": sess.codex_input_tokens if sess else 0,
                    "output_tokens": sess.codex_output_tokens if sess else 0,
                    "total_tokens": sess.codex_total_tokens if sess else 0,
                } if sess else {},
            })

        retrying_rows = []
        for issue_id, entry in self._state.retry_attempts.items():
            due_dt = datetime.fromtimestamp(entry.due_at_ms / 1000, tz=timezone.utc)
            retrying_rows.append({
                "issue_id": issue_id,
                "issue_identifier": entry.identifier,
                "attempt": entry.attempt,
                "due_at": due_dt.isoformat(),
                "error": entry.error,
            })

        # Compute live seconds_running.
        active_seconds = sum(
            (now - e.started_at).total_seconds() for e in self._state.running.values()
        )
        totals = self._state.codex_totals
        seconds_running = totals.seconds_running + active_seconds

        return {
            "generated_at": now.isoformat(),
            "counts": {"running": len(running_rows), "retrying": len(retrying_rows)},
            "running": running_rows,
            "retrying": retrying_rows,
            "codex_totals": {
                "input_tokens": totals.input_tokens,
                "output_tokens": totals.output_tokens,
                "total_tokens": totals.total_tokens,
                "seconds_running": seconds_running,
            },
            "rate_limits": self._state.codex_rate_limits,
            "config_error": self._last_config_error,
        }

    def issue_detail(self, identifier: str) -> Optional[dict[str, Any]]:
        """Return debug details for one issue identifier, or None if unknown."""
        identifier_lower = identifier.lower()
        for issue_id, entry in self._state.running.items():
            if entry.identifier.lower() == identifier_lower:
                return self._build_issue_detail(issue_id, entry, status="running")
        for issue_id, retry in self._state.retry_attempts.items():
            if retry.identifier.lower() == identifier_lower:
                return self._build_issue_detail_retry(issue_id, retry)
        return None

    def _build_issue_detail(self, issue_id: str, entry: RunningEntry, status: str) -> dict[str, Any]:
        sess = entry.session
        ws_path = str(self._workspace_manager.workspace_path(entry.identifier)) if self._workspace_manager else ""
        return {
            "issue_identifier": entry.identifier,
            "issue_id": issue_id,
            "status": status,
            "workspace": {"path": ws_path},
            "attempts": {"current_retry_attempt": entry.retry_attempt},
            "running": {
                "session_id": sess.session_id if sess else None,
                "turn_count": sess.turn_count if sess else 0,
                "state": entry.issue.state,
                "started_at": entry.started_at.isoformat(),
                "last_event": sess.last_codex_event if sess else None,
                "last_message": sess.last_codex_message if sess else None,
                "last_event_at": sess.last_codex_timestamp.isoformat() if sess and sess.last_codex_timestamp else None,
                "tokens": {
                    "input_tokens": sess.codex_input_tokens if sess else 0,
                    "output_tokens": sess.codex_output_tokens if sess else 0,
                    "total_tokens": sess.codex_total_tokens if sess else 0,
                } if sess else {},
            },
            "retry": None,
            "last_error": entry.last_error,
        }

    def _build_issue_detail_retry(self, issue_id: str, retry: RetryEntry) -> dict[str, Any]:
        due_dt = datetime.fromtimestamp(retry.due_at_ms / 1000, tz=timezone.utc)
        ws_path = str(self._workspace_manager.workspace_path(retry.identifier)) if self._workspace_manager else ""
        return {
            "issue_identifier": retry.identifier,
            "issue_id": issue_id,
            "status": "retrying",
            "workspace": {"path": ws_path},
            "attempts": {"current_retry_attempt": retry.attempt},
            "running": None,
            "retry": {"attempt": retry.attempt, "due_at": due_dt.isoformat(), "error": retry.error},
            "last_error": retry.error,
        }

    def trigger_refresh(self) -> None:
        """Immediately schedule a new tick (best-effort)."""
        self._schedule_tick(delay_ms=0)

    # ------------------------------------------------------------------
    # Internal scheduling
    # ------------------------------------------------------------------

    def _schedule_tick(self, delay_ms: int) -> None:
        async def _delayed():
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)
            await self._tick()

        self._poll_task = asyncio.get_event_loop().create_task(_delayed())

    async def _tick(self) -> None:
        try:
            await self._reconcile_running()

            err = validate_dispatch_config(self._cfg)
            if err:
                log.error(f"dispatch validation=failed error={err}")
                self._last_config_error = err
                self._notify()
                self._schedule_tick(self._state.poll_interval_ms)
                return

            self._last_config_error = None

            try:
                candidates = await self._tracker.fetch_candidate_issues()
            except TrackerError as e:
                log.error(f"tracker fetch=failed error={e}", **_ec(e))
                self._notify()
                self._schedule_tick(self._state.poll_interval_ms)
                return

            for issue in sorted(candidates, key=_sort_key):
                if not self._available_slots():
                    break
                if self._should_dispatch(issue):
                    self._dispatch(issue, attempt=None)

            self._notify()
        finally:
            self._schedule_tick(self._state.poll_interval_ms)

    def _available_slots(self) -> bool:
        running_count = len(self._state.running)
        return running_count < self._state.max_concurrent_agents

    def _per_state_slots_available(self, issue: Issue) -> bool:
        state_lower = issue.state.lower()
        limit = self._cfg.agent.max_concurrent_agents_by_state.get(state_lower)
        if limit is None:
            return True
        count = sum(
            1 for e in self._state.running.values()
            if e.issue.state.lower() == state_lower
        )
        return count < limit

    def _should_dispatch(self, issue: Issue) -> bool:
        if not issue.id or not issue.identifier or not issue.title or not issue.state:
            return False
        cfg = self._cfg
        active = [s.lower() for s in cfg.tracker.active_states]
        terminal = [s.lower() for s in cfg.tracker.terminal_states]
        state_lower = issue.state.lower()
        if state_lower not in active:
            return False
        if state_lower in terminal:
            return False
        if issue.id in self._state.running:
            return False
        if issue.id in self._state.claimed:
            return False
        if not self._available_slots():
            return False
        if not self._per_state_slots_available(issue):
            return False
        if state_lower == "todo" and not _all_blockers_terminal(issue, cfg.tracker.terminal_states):
            return False
        return True

    def _dispatch(self, issue: Issue, attempt: Optional[int]) -> None:
        log.info(
            f"dispatch status=starting attempt={attempt}",
            **log.issue_ctx(issue.id, issue.identifier),
        )

        runner = AgentRunner(
            issue=issue,
            attempt=attempt,
            workspace_manager=self._workspace_manager,
            workflow=self._workflow,
            cfg_codex=self._cfg.codex,
            cfg_agent=self._cfg.agent,
            cfg_tracker=self._cfg.tracker,
            tracker_client=self._tracker,
            on_event=self._on_worker_event,
        )

        task = asyncio.get_event_loop().create_task(
            self._worker_wrapper(issue.id, runner, attempt)
        )

        self._state.running[issue.id] = RunningEntry(
            worker_task=task,
            identifier=issue.identifier,
            issue=issue,
            session=None,
            retry_attempt=attempt,
            started_at=_now(),
        )
        self._state.claimed.add(issue.id)
        self._state.retry_attempts.pop(issue.id, None)
        old_timer = self._state.retry_timers.pop(issue.id, None)
        if old_timer:
            old_timer.cancel()

    async def _worker_wrapper(
        self, issue_id: str, runner: AgentRunner, attempt: Optional[int]
    ) -> None:
        started_at = time.monotonic()
        result = await runner.run()
        elapsed = time.monotonic() - started_at
        self._on_worker_exit(result)

    def _on_worker_exit(self, result: WorkerResult) -> None:
        issue_id = result.issue_id
        entry = self._state.running.pop(issue_id, None)
        if entry is None:
            return

        self._state.codex_totals.seconds_running += (
            _now() - entry.started_at
        ).total_seconds()

        if result.outcome == WorkerOutcome.NORMAL:
            self._state.completed.add(issue_id)
            log.info(
                "worker exit=normal scheduling continuation",
                **log.issue_ctx(issue_id, entry.identifier),
            )
            self._schedule_retry(
                issue_id=issue_id,
                identifier=entry.identifier,
                attempt=1,
                delay_ms=_CONTINUATION_DELAY_MS,
                error=None,
            )
        else:
            next_attempt = (entry.retry_attempt or 0) + 1
            delay = _backoff_ms(next_attempt, self._cfg.agent.max_retry_backoff_ms)
            log.warn(
                f"worker exit=abnormal error={result.error} retry_attempt={next_attempt}",
                **log.issue_ctx(issue_id, entry.identifier),
            )
            self._schedule_retry(
                issue_id=issue_id,
                identifier=entry.identifier,
                attempt=next_attempt,
                delay_ms=delay,
                error=result.error,
            )
        self._notify()

    def _schedule_retry(
        self,
        issue_id: str,
        identifier: str,
        attempt: int,
        delay_ms: int,
        error: Optional[str],
    ) -> None:
        # Cancel any existing timer.
        old = self._state.retry_timers.pop(issue_id, None)
        if old:
            old.cancel()

        due_at_ms = _mono_ms() + delay_ms
        self._state.retry_attempts[issue_id] = RetryEntry(
            issue_id=issue_id,
            identifier=identifier,
            attempt=attempt,
            due_at_ms=due_at_ms,
            error=error,
        )

        async def _fire():
            await asyncio.sleep(delay_ms / 1000)
            await self._on_retry_timer(issue_id)

        timer_task = asyncio.get_event_loop().create_task(_fire())
        self._state.retry_timers[issue_id] = timer_task

    async def _on_retry_timer(self, issue_id: str) -> None:
        retry_entry = self._state.retry_attempts.pop(issue_id, None)
        self._state.retry_timers.pop(issue_id, None)
        if retry_entry is None:
            return

        try:
            candidates = await self._tracker.fetch_candidate_issues()
        except TrackerError as e:
            log.warn(f"retry poll=failed error={e} requeueing")
            self._schedule_retry(
                issue_id=issue_id,
                identifier=retry_entry.identifier,
                attempt=retry_entry.attempt + 1,
                delay_ms=_backoff_ms(retry_entry.attempt + 1, self._cfg.agent.max_retry_backoff_ms),
                error="retry poll failed",
            )
            return

        issue = next((c for c in candidates if c.id == issue_id), None)
        if issue is None:
            log.info(
                "retry release=not_found",
                issue_id=issue_id,
                identifier=retry_entry.identifier,
            )
            self._state.claimed.discard(issue_id)
            return

        if not self._available_slots():
            self._schedule_retry(
                issue_id=issue_id,
                identifier=retry_entry.identifier,
                attempt=retry_entry.attempt + 1,
                delay_ms=_backoff_ms(retry_entry.attempt + 1, self._cfg.agent.max_retry_backoff_ms),
                error="no available orchestrator slots",
            )
            return

        self._dispatch(issue, attempt=retry_entry.attempt)
        self._notify()

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    async def _reconcile_running(self) -> None:
        await self._reconcile_stalled()
        if not self._state.running:
            return
        running_ids = list(self._state.running.keys())
        try:
            refreshed = await self._tracker.fetch_issue_states_by_ids(running_ids)
        except TrackerError as e:
            log.debug(f"reconcile refresh=failed keep workers running error={e}")
            return

        terminal_states = self._cfg.tracker.terminal_states
        active_states = self._cfg.tracker.active_states
        refreshed_map = {i.id: i for i in refreshed}

        for issue_id in list(self._state.running.keys()):
            issue = refreshed_map.get(issue_id)
            if issue is None:
                # Not returned — leave running.
                continue
            if _is_terminal(issue.state, terminal_states):
                log.info(
                    f"reconcile action=terminate_terminal state={issue.state}",
                    **log.issue_ctx(issue_id, issue.identifier),
                )
                await self._terminate_running(issue_id, cleanup_workspace=True)
            elif _is_active(issue.state, active_states):
                # Update the in-memory snapshot.
                if issue_id in self._state.running:
                    self._state.running[issue_id].issue = issue
            else:
                log.info(
                    f"reconcile action=terminate_non_active state={issue.state}",
                    **log.issue_ctx(issue_id, issue.identifier),
                )
                await self._terminate_running(issue_id, cleanup_workspace=False)

    async def _reconcile_stalled(self) -> None:
        stall_ms = self._cfg.codex.stall_timeout_ms
        if stall_ms <= 0:
            return
        now = _now()
        for issue_id, entry in list(self._state.running.items()):
            sess = entry.session
            if sess and sess.last_codex_timestamp:
                elapsed_ms = (now - sess.last_codex_timestamp).total_seconds() * 1000
            else:
                elapsed_ms = (now - entry.started_at).total_seconds() * 1000
            if elapsed_ms > stall_ms:
                log.warn(
                    f"stall detected elapsed_ms={elapsed_ms:.0f}",
                    **log.issue_ctx(issue_id, entry.identifier),
                )
                await self._terminate_running(issue_id, cleanup_workspace=False)
                next_attempt = (entry.retry_attempt or 0) + 1
                self._schedule_retry(
                    issue_id=issue_id,
                    identifier=entry.identifier,
                    attempt=next_attempt,
                    delay_ms=_backoff_ms(next_attempt, self._cfg.agent.max_retry_backoff_ms),
                    error="stall timeout",
                )

    async def _terminate_running(self, issue_id: str, cleanup_workspace: bool) -> None:
        entry = self._state.running.pop(issue_id, None)
        if entry is None:
            return
        self._state.claimed.discard(issue_id)
        entry.worker_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(entry.worker_task), timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass

        if cleanup_workspace and self._workspace_manager:
            try:
                await self._workspace_manager.remove_workspace(entry.identifier)
            except Exception as e:
                log.warn(f"workspace cleanup=failed error={e}", identifier=entry.identifier)

        self._state.codex_totals.seconds_running += (
            _now() - entry.started_at
        ).total_seconds()

    # ------------------------------------------------------------------
    # Startup cleanup
    # ------------------------------------------------------------------

    async def _startup_terminal_cleanup(self) -> None:
        try:
            terminal_issues = await self._tracker.fetch_issues_by_states(
                self._cfg.tracker.terminal_states
            )
        except TrackerError as e:
            log.warn(f"startup terminal_cleanup=failed error={e}")
            return

        for issue in terminal_issues:
            try:
                await self._workspace_manager.remove_workspace(issue.identifier)
            except Exception as e:
                log.warn(f"startup workspace_cleanup=failed error={e}", identifier=issue.identifier)

    # ------------------------------------------------------------------
    # Worker event handler
    # ------------------------------------------------------------------

    def _on_worker_event(self, issue_id: str, event: dict) -> None:
        entry = self._state.running.get(issue_id)
        if entry is None:
            return

        evt_type = event.get("event", "")
        ts_str = event.get("timestamp")
        ts = None
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                ts = _now()

        # Update or initialize session.
        if evt_type == "session_started":
            thread_id = event.get("thread_id", "")
            pid = event.get("codex_app_server_pid")
            entry.session = LiveSession(
                session_id=f"{thread_id}-",
                thread_id=thread_id,
                turn_id="",
                codex_app_server_pid=pid,
                last_codex_event=evt_type,
                last_codex_timestamp=ts or _now(),
            )
        elif entry.session is not None:
            sess = entry.session
            sess.last_codex_event = evt_type
            sess.last_codex_timestamp = ts or _now()
            if "message" in event:
                sess.last_codex_message = str(event["message"])[:500]

            # Update turn ID if present.
            if "turn_id" in event:
                sess.turn_id = event["turn_id"]
                sess.session_id = f"{sess.thread_id}-{sess.turn_id}"

            if evt_type == "streaming_turn":
                sess.turn_count += 1

            # Token accounting — prefer absolute thread totals.
            self._update_tokens(sess, event)

        # Rate limits.
        if "rate_limits" in event:
            self._state.codex_rate_limits = event["rate_limits"]

        log.debug(
            f"agent_event={evt_type}",
            **log.issue_ctx(issue_id, entry.identifier),
            **(log.session_ctx(entry.session.session_id) if entry.session else {}),
        )

    def _update_tokens(self, sess: LiveSession, event: dict) -> None:
        # Prefer thread/tokenUsage/updated absolute counts.
        usage = None
        evt = event.get("event", "")
        if evt in ("thread/tokenUsage/updated",) or "total_token_usage" in event:
            usage = event.get("total_token_usage") or event.get("usage")
        elif "usage" in event and evt not in ("last_token_usage",):
            usage = event["usage"]

        if usage and isinstance(usage, dict):
            inp = usage.get("input_tokens") or usage.get("inputTokens") or 0
            out = usage.get("output_tokens") or usage.get("outputTokens") or 0
            total = usage.get("total_tokens") or usage.get("totalTokens") or (inp + out)

            # Compute deltas relative to last reported to avoid double counting.
            d_in = max(0, inp - sess.last_reported_input_tokens)
            d_out = max(0, out - sess.last_reported_output_tokens)
            d_total = max(0, total - sess.last_reported_total_tokens)

            sess.codex_input_tokens += d_in
            sess.codex_output_tokens += d_out
            sess.codex_total_tokens += d_total
            sess.last_reported_input_tokens = inp
            sess.last_reported_output_tokens = out
            sess.last_reported_total_tokens = total

            self._state.codex_totals.input_tokens += d_in
            self._state.codex_totals.output_tokens += d_out
            self._state.codex_totals.total_tokens += d_total


def _ec(e: Exception) -> dict:
    return {"error_code": getattr(e, "code", "unknown")}
