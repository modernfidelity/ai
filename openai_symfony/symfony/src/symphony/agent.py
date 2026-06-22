"""Codex app-server subprocess client and agent runner."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import log
from .config import CodexConfig
from .models import Issue, LiveSession, WorkerOutcome, WorkerResult
from .workspace import Workspace, WorkspaceError

# Maximum JSON line size accepted from the app-server (10 MB per spec).
_MAX_LINE_BYTES = 10 * 1024 * 1024


class AgentError(Exception):
    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ms() -> int:
    return int(time.monotonic() * 1000)


# ---------------------------------------------------------------------------
# App-server protocol client
# ---------------------------------------------------------------------------

class AppServerClient:
    """Manages one codex app-server subprocess and speaks its JSON-lines protocol."""

    def __init__(self, cfg: CodexConfig, workspace_path: str) -> None:
        self._cfg = cfg
        self._workspace = workspace_path
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._thread_id: Optional[str] = None
        self._req_id = 0

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc else None

    @property
    def thread_id(self) -> Optional[str]:
        return self._thread_id

    async def start(self) -> None:
        """Launch the app-server subprocess."""
        cmd = self._cfg.command
        try:
            self._proc = await asyncio.create_subprocess_shell(
                f"bash -lc {_shell_quote(cmd)}",
                cwd=self._workspace,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_MAX_LINE_BYTES,
            )
        except OSError as e:
            raise AgentError("codex_not_found", f"Failed to launch codex app-server: {e}") from e

        # Initialize the session.
        try:
            init_resp = await asyncio.wait_for(
                self._rpc("initialize", {"clientInfo": {"name": "symphony", "version": "0.1.0"}}),
                timeout=self._cfg.read_timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            await self._kill()
            raise AgentError("response_timeout", "Timed out waiting for app-server initialization")

        if init_resp.get("error"):
            await self._kill()
            raise AgentError("response_error", f"App-server init error: {init_resp['error']}")

    async def start_thread(self, cwd: str, approval_policy: Optional[str], sandbox: Optional[str]) -> str:
        """Create a new coding thread; returns thread_id."""
        params: dict[str, Any] = {"workingDirectory": cwd}
        if approval_policy:
            params["approvalPolicy"] = approval_policy
        if sandbox:
            params["sandbox"] = sandbox

        try:
            resp = await asyncio.wait_for(
                self._rpc("thread/start", params),
                timeout=self._cfg.read_timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            raise AgentError("response_timeout", "Timed out waiting for thread/start response")

        if resp.get("error"):
            raise AgentError("response_error", f"thread/start error: {resp['error']}")

        thread_id = (resp.get("result") or {}).get("threadId") or resp.get("threadId")
        if not thread_id:
            raise AgentError("response_error", "thread/start returned no threadId")

        self._thread_id = thread_id
        return thread_id

    async def run_turn(
        self,
        thread_id: str,
        prompt: str,
        issue: Issue,
        turn_timeout_ms: int,
        on_event: Callable[[dict[str, Any]], None],
        linear_graphql_handler: Optional[Callable[[dict[str, Any]], Any]] = None,
    ) -> tuple[str, bool]:
        """
        Start a turn on the given thread and stream events until completion.
        Returns (turn_id, success).
        """
        title = f"{issue.identifier}: {issue.title}"
        params: dict[str, Any] = {
            "threadId": thread_id,
            "message": prompt,
            "title": title,
        }

        try:
            resp = await asyncio.wait_for(
                self._rpc("turn/start", params),
                timeout=self._cfg.read_timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            raise AgentError("response_timeout", "Timed out waiting for turn/start response")

        if resp.get("error"):
            raise AgentError("response_error", f"turn/start error: {resp['error']}")

        turn_id = (resp.get("result") or {}).get("turnId") or resp.get("turnId")
        if not turn_id:
            raise AgentError("response_error", "turn/start returned no turnId")

        success = await self._stream_turn(
            turn_id=turn_id,
            thread_id=thread_id,
            timeout_ms=turn_timeout_ms,
            on_event=on_event,
            linear_graphql_handler=linear_graphql_handler,
        )
        return turn_id, success

    async def _stream_turn(
        self,
        turn_id: str,
        thread_id: str,
        timeout_ms: int,
        on_event: Callable[[dict[str, Any]], None],
        linear_graphql_handler: Optional[Callable[[dict[str, Any]], Any]],
    ) -> bool:
        """Stream events from the app-server until the turn completes. Returns success flag."""
        deadline = asyncio.get_event_loop().time() + timeout_ms / 1000

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise AgentError("turn_timeout", f"Turn {turn_id} exceeded timeout {timeout_ms}ms")

            try:
                line = await asyncio.wait_for(
                    self._readline(),
                    timeout=min(remaining, self._cfg.read_timeout_ms / 1000),
                )
            except asyncio.TimeoutError:
                # Check if turn timeout exceeded
                if asyncio.get_event_loop().time() >= deadline:
                    raise AgentError("turn_timeout", f"Turn {turn_id} exceeded timeout {timeout_ms}ms")
                continue

            if line is None:
                # Subprocess exited.
                raise AgentError("port_exit", "App-server subprocess exited unexpectedly")

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                on_event({"event": "malformed", "raw": line[:200]})
                continue

            event_type = msg.get("event") or msg.get("type") or "other_message"
            on_event({**msg, "event": event_type})

            # Handle tool calls from the agent.
            if event_type in ("tool/call", "tool_call"):
                await self._handle_tool_call(msg, linear_graphql_handler)
                continue

            # Handle approval requests — auto-approve by default (high-trust policy).
            if event_type in ("approval/request", "approval_request"):
                await self._auto_approve(msg)
                continue

            # Turn completion signals.
            if event_type in ("turn/complete", "turn_completed"):
                return True
            if event_type in ("turn/failed", "turn_failed", "turn_ended_with_error"):
                raise AgentError("turn_failed", msg.get("message", "Turn failed"))
            if event_type in ("turn/cancelled", "turn_cancelled"):
                raise AgentError("turn_cancelled", "Turn was cancelled")
            if event_type in ("turn/inputRequired", "turn_input_required"):
                # High-trust policy: fail immediately on user input requests.
                raise AgentError("turn_input_required", "Turn requires user input (not supported)")

    async def _handle_tool_call(
        self,
        msg: dict[str, Any],
        linear_graphql_handler: Optional[Callable[[dict[str, Any]], Any]],
    ) -> None:
        call_id = msg.get("callId") or msg.get("id")
        tool_name = msg.get("toolName") or msg.get("name") or ""
        tool_input = msg.get("input") or msg.get("arguments") or {}

        if tool_name == "linear_graphql" and linear_graphql_handler is not None:
            try:
                result = await linear_graphql_handler(tool_input)
                await self._send({"method": "tool/result", "params": {
                    "callId": call_id,
                    "success": True,
                    "result": result,
                }})
            except Exception as e:
                await self._send({"method": "tool/result", "params": {
                    "callId": call_id,
                    "success": False,
                    "error": str(e),
                }})
        else:
            # Unsupported tool — return failure without stalling.
            await self._send({"method": "tool/result", "params": {
                "callId": call_id,
                "success": False,
                "error": f"Tool '{tool_name}' is not supported by this Symphony instance",
            }})

    async def _auto_approve(self, msg: dict[str, Any]) -> None:
        approval_id = msg.get("approvalId") or msg.get("id")
        await self._send({"method": "approval/response", "params": {
            "approvalId": approval_id,
            "approved": True,
        }})

    async def stop(self) -> None:
        if self._proc is None:
            return
        try:
            await self._send({"method": "thread/stop", "params": {}})
        except Exception:
            pass
        await self._kill()

    async def _kill(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.kill()
                await self._proc.wait()
            except Exception:
                pass

    def _next_id(self) -> str:
        self._req_id += 1
        return str(self._req_id)

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = self._next_id()
        await self._send({"id": req_id, "method": method, "params": params})
        # Read until we get a response for this id.
        while True:
            line = await self._readline()
            if line is None:
                raise AgentError("port_exit", "App-server exited before responding")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(msg.get("id")) == req_id:
                return msg
            # Other messages (events) are discarded during RPC startup.

    async def _send(self, msg: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        line = json.dumps(msg) + "\n"
        self._proc.stdin.write(line.encode())
        await self._proc.stdin.drain()

    async def _readline(self) -> Optional[str]:
        if self._proc is None or self._proc.stdout is None:
            return None
        try:
            line = await self._proc.stdout.readline()
        except Exception:
            return None
        if not line:
            return None
        return line.decode(errors="replace").rstrip("\n\r")


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

class AgentRunner:
    """
    Combines workspace preparation, prompt rendering, and app-server client
    into a single worker run.
    """

    def __init__(
        self,
        issue: Issue,
        attempt: Optional[int],
        workspace_manager: Any,  # WorkspaceManager
        workflow: Any,           # WorkflowDefinition
        cfg_codex: CodexConfig,
        cfg_agent: Any,          # AgentConfig
        cfg_tracker: Any,        # TrackerConfig
        tracker_client: Any,     # LinearClient
        on_event: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self._issue = issue
        self._attempt = attempt
        self._wm = workspace_manager
        self._workflow = workflow
        self._cfg_codex = cfg_codex
        self._cfg_agent = cfg_agent
        self._tracker = tracker_client
        self._on_event = on_event
        self._client: Optional[AppServerClient] = None

    async def run(self) -> WorkerResult:
        issue = self._issue
        started_at = time.monotonic()

        def emit(event: str, **kwargs: Any) -> None:
            self._on_event(issue.id, {"event": event, "timestamp": _now_utc().isoformat(), **kwargs})

        # 1. Prepare workspace.
        emit("preparing_workspace")
        try:
            ws = await self._wm.create_for_issue(issue.identifier)
        except WorkspaceError as e:
            emit("startup_failed", error=str(e))
            return WorkerResult(
                issue_id=issue.id,
                outcome=WorkerOutcome.ABNORMAL,
                error=str(e),
                runtime_seconds=time.monotonic() - started_at,
            )

        # 2. Run before_run hook.
        from pathlib import Path
        ws_path = Path(ws.path)
        try:
            await self._wm.run_before_run(ws_path, issue.identifier)
        except WorkspaceError as e:
            emit("startup_failed", error=str(e), phase="before_run")
            return WorkerResult(
                issue_id=issue.id,
                outcome=WorkerOutcome.ABNORMAL,
                error=f"before_run hook: {e}",
                runtime_seconds=time.monotonic() - started_at,
            )

        # 3. Start app-server session.
        emit("launching_agent_process")
        client = AppServerClient(self._cfg_codex, ws.path)
        self._client = client
        try:
            await client.start()
        except AgentError as e:
            await self._wm.run_after_run(ws_path, issue.identifier)
            emit("startup_failed", error=str(e))
            return WorkerResult(
                issue_id=issue.id,
                outcome=WorkerOutcome.ABNORMAL,
                error=str(e),
                runtime_seconds=time.monotonic() - started_at,
            )

        emit("session_started", codex_app_server_pid=client.pid)

        # 4. Create thread.
        try:
            thread_id = await client.start_thread(
                cwd=ws.path,
                approval_policy=self._cfg_codex.approval_policy,
                sandbox=self._cfg_codex.thread_sandbox,
            )
        except AgentError as e:
            await client.stop()
            await self._wm.run_after_run(ws_path, issue.identifier)
            emit("startup_failed", error=str(e))
            return WorkerResult(
                issue_id=issue.id,
                outcome=WorkerOutcome.ABNORMAL,
                error=str(e),
                runtime_seconds=time.monotonic() - started_at,
            )

        # 5. Turn loop.
        from .workflow import render_prompt, WorkflowError
        max_turns = self._cfg_agent.max_turns
        turn_number = 1
        attempt = self._attempt

        while True:
            emit("building_prompt", turn=turn_number)
            try:
                if turn_number == 1:
                    prompt = render_prompt(self._workflow.prompt_template, issue, attempt)
                else:
                    # Continuation guidance — don't resend full prompt.
                    prompt = (
                        f"Continue working on {issue.identifier}: {issue.title}. "
                        f"You are on turn {turn_number} of {max_turns}. "
                        "Check the current status and continue making progress."
                    )
            except WorkflowError as e:
                await client.stop()
                await self._wm.run_after_run(ws_path, issue.identifier)
                emit("startup_failed", error=str(e), phase="prompt_render")
                return WorkerResult(
                    issue_id=issue.id,
                    outcome=WorkerOutcome.ABNORMAL,
                    error=f"prompt render: {e}",
                    runtime_seconds=time.monotonic() - started_at,
                )

            emit("streaming_turn", turn=turn_number, thread_id=thread_id)

            def _on_codex_event(evt: dict[str, Any]) -> None:
                emit(**evt)

            try:
                turn_id, success = await client.run_turn(
                    thread_id=thread_id,
                    prompt=prompt,
                    issue=issue,
                    turn_timeout_ms=self._cfg_codex.turn_timeout_ms,
                    on_event=_on_codex_event,
                    linear_graphql_handler=self._make_linear_graphql_handler(),
                )
            except AgentError as e:
                await client.stop()
                await self._wm.run_after_run(ws_path, issue.identifier)
                code = e.code
                status = "timed_out" if code == "turn_timeout" else "turn_failed"
                emit(f"turn_{status}", error=str(e))
                return WorkerResult(
                    issue_id=issue.id,
                    outcome=WorkerOutcome.ABNORMAL,
                    error=str(e),
                    runtime_seconds=time.monotonic() - started_at,
                )

            emit("turn_completed", turn=turn_number, turn_id=turn_id)

            # Refresh issue state from tracker.
            try:
                refreshed = await self._tracker.fetch_issue_states_by_ids([issue.id])
                if refreshed:
                    issue = refreshed[0]
            except Exception as e:
                await client.stop()
                await self._wm.run_after_run(ws_path, issue.identifier)
                return WorkerResult(
                    issue_id=issue.id,
                    outcome=WorkerOutcome.ABNORMAL,
                    error=f"issue state refresh: {e}",
                    runtime_seconds=time.monotonic() - started_at,
                )

            from .config import TrackerConfig as TC
            active_states_lower = [s.lower() for s in self._cfg_agent.max_concurrent_agents_by_state.keys()]
            # Use the tracker config active states from the tracker client.
            if not _is_active(issue.state, self._tracker._cfg.active_states):
                break

            if turn_number >= max_turns:
                break

            turn_number += 1

        await client.stop()
        await self._wm.run_after_run(ws_path, issue.identifier)
        emit("finishing", turns_completed=turn_number)

        return WorkerResult(
            issue_id=issue.id,
            outcome=WorkerOutcome.NORMAL,
            runtime_seconds=time.monotonic() - started_at,
        )

    async def cancel(self) -> None:
        """Cancel the running agent (called by reconciliation)."""
        if self._client:
            await self._client.stop()

    def make_linear_graphql_handler(self) -> Optional[Callable]:
        return self.make_linear_graphql_handler_impl()

    def make_linear_graphql_handler_impl(self) -> Optional[Callable]:
        return self._make_linear_graphql_handler()

    def _make_linear_graphql_handler(self) -> Optional[Callable]:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            query = args.get("query", "")
            variables = args.get("variables") or {}
            if not query or not isinstance(query, str):
                return {"success": False, "error": "query must be a non-empty string"}
            if not isinstance(variables, dict):
                return {"success": False, "error": "variables must be an object"}
            try:
                data = await self._tracker._graphql(query, variables)
                return {"success": True, "data": data}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return handler


def _is_active(state: str, active_states: list[str]) -> bool:
    return state.lower() in [s.lower() for s in active_states]
