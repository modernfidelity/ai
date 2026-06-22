"""WORKFLOW.md loader, parser, and prompt renderer."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from jinja2 import Environment, StrictUndefined, TemplateError, UndefinedError

from .config import ConfigError, ServiceConfig, load_config
from .models import Issue, WorkflowDefinition


class WorkflowError(Exception):
    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_workflow(path: Path) -> WorkflowDefinition:
    """Parse WORKFLOW.md and return WorkflowDefinition. Raises WorkflowError on any failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise WorkflowError("missing_workflow_file", f"Cannot read workflow file: {e}") from e

    config: dict[str, Any] = {}
    prompt_body = text

    if text.startswith("---"):
        lines = text.splitlines(keepends=True)
        end = None
        for i, line in enumerate(lines[1:], 1):
            if line.rstrip("\n\r") == "---":
                end = i
                break
        if end is not None:
            front_matter_text = "".join(lines[1:end])
            prompt_body = "".join(lines[end + 1 :])
            try:
                parsed = yaml.safe_load(front_matter_text)
            except yaml.YAMLError as e:
                raise WorkflowError("workflow_parse_error", f"YAML parse error: {e}") from e
            if parsed is None:
                parsed = {}
            if not isinstance(parsed, dict):
                raise WorkflowError(
                    "workflow_front_matter_not_a_map",
                    "YAML front matter must be a mapping/object",
                )
            config = parsed

    return WorkflowDefinition(config=config, prompt_template=prompt_body.strip())


def load_workflow_and_config(path: Path) -> tuple[WorkflowDefinition, ServiceConfig]:
    wf = load_workflow(path)
    cfg = load_config(wf.config, path)
    return wf, cfg


_JINJA_ENV = Environment(undefined=StrictUndefined, keep_trailing_newline=True)


def render_prompt(template_str: str, issue: Issue, attempt: Optional[int]) -> str:
    """Render the workflow prompt template. Raises WorkflowError on any failure."""
    if not template_str:
        return "You are working on an issue from Linear."

    try:
        tmpl = _JINJA_ENV.from_string(template_str)
    except TemplateError as e:
        raise WorkflowError("template_parse_error", f"Template parse error: {e}") from e

    ctx: dict[str, Any] = {
        "issue": issue.to_template_dict(),
        "attempt": attempt,
    }
    try:
        return tmpl.render(**ctx)
    except UndefinedError as e:
        raise WorkflowError("template_render_error", f"Unknown template variable: {e}") from e
    except TemplateError as e:
        raise WorkflowError("template_render_error", f"Template render error: {e}") from e


class WorkflowWatcher:
    """Watch WORKFLOW.md for changes and call the reload callback asynchronously."""

    def __init__(
        self,
        path: Path,
        on_change: Callable[[WorkflowDefinition, ServiceConfig], None],
        on_error: Callable[[WorkflowError | ConfigError], None],
    ) -> None:
        self._path = path
        self._on_change = on_change
        self._on_error = on_error
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._task = asyncio.get_event_loop().create_task(self._watch())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _watch(self) -> None:
        try:
            from watchfiles import awatch
        except ImportError:
            return  # watchfiles not installed; skip watching

        async for _ in awatch(str(self._path)):
            try:
                wf, cfg = load_workflow_and_config(self._path)
                self._on_change(wf, cfg)
            except (WorkflowError, ConfigError) as e:
                self._on_error(e)
