"""Databricks SQL Warehouse connectivity check.

Fill in tools/.env (see .env.example), then run:

    uv run check_databricks.py

It opens a connection, runs a trivial query, and prints the result — a quick way
to confirm your credentials and HTTP path are correct before wiring `run_sql`
into an MCP client.
"""

import os
import sys

from dotenv import load_dotenv

from server import run_sql

load_dotenv()

REQUIRED = ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")


def main() -> int:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your credentials.")
        return 1

    print(f"Connecting to {os.environ['DATABRICKS_HOST']} ...")
    try:
        result = run_sql("SELECT current_catalog() AS catalog, 1 AS ping", max_rows=1)
    except Exception as exc:  # noqa: BLE001 - surface any connection error to the user
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1

    print("OK — query returned:")
    print(f"  columns: {result['columns']}")
    print(f"  rows:    {result['rows']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
