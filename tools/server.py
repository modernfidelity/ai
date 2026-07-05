"""Example FastMCP server.

Demonstrates three kinds of tools exposed over MCP:

1. A Databricks SQL Warehouse query tool.
2. A pure-Python custom function (no external I/O).
3. A 3rd-party REST API call.

Run it:

    # stdio (for Claude Desktop / Claude Code)
    uv run server.py

    # or over HTTP
    uv run server.py --http

Configure credentials via a .env file (see .env.example).
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from typing import Any

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

mcp = FastMCP(
    name="example-tools",
    instructions=(
        "Example server exposing a Databricks SQL query tool, a local Python "
        "utility, and a 3rd-party REST API lookup. Use `run_sql` for warehouse "
        "data, `working_days_between` for date math, and `get_exchange_rate` "
        "for FX rates."
    ),
)


# ---------------------------------------------------------------------------
# 1. Databricks SQL Warehouse
# ---------------------------------------------------------------------------
def _databricks_connection():
    """Open a connection to a Databricks SQL Warehouse.

    Imported lazily so the server still starts if the optional dependency or
    credentials are missing (the other tools remain usable).
    """
    from databricks import sql  # pip install databricks-sql-connector

    host = os.environ["DATABRICKS_HOST"]          # e.g. adb-1234.5.azuredatabricks.net
    http_path = os.environ["DATABRICKS_HTTP_PATH"]  # e.g. /sql/1.0/warehouses/abc123
    token = os.environ["DATABRICKS_TOKEN"]          # personal access token / OAuth

    return sql.connect(
        server_hostname=host,
        http_path=http_path,
        access_token=token,
    )


@mcp.tool
def run_sql(query: str, max_rows: int = 100) -> dict[str, Any]:
    """Run a read-only SQL query against the Databricks SQL Warehouse.

    Args:
        query: A single SELECT statement. Do not run DDL/DML here.
        max_rows: Maximum number of rows to return (guards against huge results).

    Returns:
        A dict with `columns` (list of names) and `rows` (list of row lists).
    """
    lowered = query.strip().lower()
    if not lowered.startswith(("select", "with", "show", "describe")):
        raise ValueError("Only read-only queries (SELECT/WITH/SHOW/DESCRIBE) are allowed.")

    with _databricks_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            columns = [c[0] for c in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(max_rows)

    return {
        "columns": columns,
        "rows": [list(r) for r in rows],
        "row_count": len(rows),
        "truncated": len(rows) == max_rows,
    }


# ---------------------------------------------------------------------------
# 2. Custom Python function (pure, no external calls)
# ---------------------------------------------------------------------------
@mcp.tool
def working_days_between(start: str, end: str) -> dict[str, Any]:
    """Count working days (Mon-Fri) between two ISO dates, inclusive of start,
    exclusive of end.

    Args:
        start: Start date, ISO format YYYY-MM-DD.
        end: End date, ISO format YYYY-MM-DD.

    Returns:
        A dict with the working-day count and the total calendar-day span.
    """
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


# ---------------------------------------------------------------------------
# 3. Third-party REST API call
# ---------------------------------------------------------------------------
@mcp.tool
def get_exchange_rate(base: str = "USD", target: str = "GBP") -> dict[str, Any]:
    """Fetch the current exchange rate from a public REST API.

    Uses the free Frankfurter API (https://frankfurter.dev) — no API key needed.

    Args:
        base: Base currency code, e.g. "USD".
        target: Target currency code, e.g. "GBP".

    Returns:
        A dict with the rate and the reference date reported by the API.
    """
    base, target = base.upper(), target.upper()
    url = "https://api.frankfurter.dev/v1/latest"

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url, params={"base": base, "symbols": target})
        resp.raise_for_status()
        data = resp.json()

    rate = data.get("rates", {}).get(target)
    if rate is None:
        raise ValueError(f"No rate returned for {base}->{target}. Check currency codes.")

    return {
        "base": base,
        "target": target,
        "rate": rate,
        "as_of": data.get("date"),
    }


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="http", host="127.0.0.1", port=8000)
    else:
        mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
