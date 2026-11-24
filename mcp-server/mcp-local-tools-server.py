"""Local tools MCP server.

Run it:

    uv run mcp-local-tools-server.py          # stdio (for Claude Code / Claude Desktop)
    uv run mcp-local-tools-server.py --http   # HTTP on http://127.0.0.1:8000
"""

import platform
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP

mcp = FastMCP("Local Tools")


@mcp.tool
def add(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


@mcp.tool
def list_directory(path: str = ".") -> list[str]:
    """List the names of files and folders inside a directory."""
    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        raise ValueError(f"{target} is not a directory")
    return sorted(p.name for p in target.iterdir())


@mcp.tool
def read_text_file(path: str, max_chars: int = 5000) -> str:
    """Read the contents of a text file, truncated to max_chars."""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError(f"{target} is not a file")
    return target.read_text(errors="replace")[:max_chars]


@mcp.tool
def system_info() -> dict:
    """Return basic information about the local machine."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }


@mcp.tool
def roll_dice(sides: int = 6, count: int = 1) -> list[int]:
    """Roll `count` dice each with `sides` faces and return the results."""
    return [random.randint(1, sides) for _ in range(count)]


@mcp.tool
def working_days_between(start: str, end: str) -> dict[str, Any]:
    """Count working days (Mon-Fri) between two ISO dates (YYYY-MM-DD),
    inclusive of start, exclusive of end."""
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    if end_d < start_d:
        raise ValueError("`end` must not be before `start`.")

    working = 0
    cursor = start_d
    while cursor < end_d:
        if cursor.weekday() < 5:  # 0=Mon .. 4=Fri
            working += 1
        cursor += timedelta(days=1)

    return {
        "start": start,
        "end": end,
        "working_days": working,
        "calendar_days": (end_d - start_d).days,
    }


@mcp.tool
def get_exchange_rate(base: str = "USD", target: str = "GBP") -> dict[str, Any]:
    """Fetch the latest exchange rate between two currency codes (e.g. USD, GBP)
    from the free Frankfurter API (https://frankfurter.dev). No API key needed."""
    base, target = base.upper(), target.upper()
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            "https://api.frankfurter.dev/v1/latest",
            params={"base": base, "symbols": target},
        )
        resp.raise_for_status()
        data = resp.json()

    rate = data.get("rates", {}).get(target)
    if rate is None:
        raise ValueError(f"No rate returned for {base}->{target}. Check currency codes.")
    return {"base": base, "target": target, "rate": rate, "as_of": data.get("date")}


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="http", host="127.0.0.1", port=8000)
    else:
        mcp.run()  # stdio
