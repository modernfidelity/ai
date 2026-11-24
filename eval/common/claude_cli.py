"""Model backend that runs Claude through headless Claude Code (`claude -p`).

Uses your Claude Code login, so no Anthropic API key is needed. To keep calls
close to a plain API call, it:
  - replaces Claude Code's system prompt (--system-prompt)
  - disables every built-in tool (--tools "")
  - runs from an empty temp dir, so no project CLAUDE.md / settings are picked up
  - doesn't save sessions (--no-session-persistence)

Usage counts toward your Claude plan's limits. `cost_usd` is Claude Code's
list-price estimate, not a bill.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass

DEFAULT_SYSTEM = "You are a helpful assistant."
_WORKDIR = tempfile.mkdtemp(prefix="eval-claude-cli-")


@dataclass
class Completion:
    text: str
    model: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int


class ClaudeCLIError(RuntimeError):
    pass


def complete(
    prompt: str,
    model: str = "haiku",
    system: str = DEFAULT_SYSTEM,
    effort: str | None = None,
    timeout: float = 300,
) -> Completion:
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--system-prompt", system,
        "--tools", "",
        "--no-session-persistence",
        "--output-format", "json",
    ]
    if effort:
        cmd += ["--effort", effort]
    try:
        proc = subprocess.run(
            cmd, cwd=_WORKDIR, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        raise ClaudeCLIError("`claude` CLI not found on PATH")
    except subprocess.TimeoutExpired:
        raise ClaudeCLIError(f"claude -p timed out after {timeout}s")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeCLIError(
            f"claude -p exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:500]}"
        )
    if data.get("is_error"):
        raise ClaudeCLIError(f"claude -p error: {data.get('result') or data}")

    usage = data.get("usage", {})
    model_usage = data.get("modelUsage", {})
    return Completion(
        text=(data.get("result") or "").strip(),
        model=next(iter(model_usage), model),
        stop_reason=data.get("stop_reason"),
        input_tokens=usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cost_usd=data.get("total_cost_usd", 0.0),
        duration_ms=data.get("duration_ms", 0),
    )
