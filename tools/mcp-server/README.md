# Example FastMCP Server

A minimal [FastMCP](https://gofastmcp.com) server showing three common tool patterns:

| Tool | Type | What it does |
|------|------|--------------|
| `run_sql` | Databricks | Runs a read-only query against a Databricks SQL Warehouse |
| `working_days_between` | Custom Python | Pure local function — counts Mon–Fri days between two dates |
| `get_exchange_rate` | 3rd-party REST | Calls the public Frankfurter FX API (no key required) |

Managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
cd tools
uv sync                 # creates .venv and installs dependencies
cp .env.example .env    # then fill in your Databricks credentials
```

## Run

```bash
# stdio transport (for Claude Desktop / Claude Code)
uv run server.py

# HTTP transport on http://127.0.0.1:8000
uv run server.py --http
```

## Test

```bash
uv run smoke_test.py        # exercises the two credential-free tools
uv run check_databricks.py  # verifies Databricks connectivity (needs .env)
```

## Register with Claude Code

```bash
claude mcp add example-tools -- uv --directory /path/to/ai/tools run server.py
```

Or add to your MCP client config manually:

```json
{
  "mcpServers": {
    "example-tools": {
      "command": "uv",
      "args": ["--directory", "/path/to/ai/tools", "run", "server.py"]
    }
  }
}
```

## Notes

- `run_sql` only permits `SELECT`/`WITH`/`SHOW`/`DESCRIBE` statements and caps
  returned rows via `max_rows`. Tighten this further for production use.
- The Databricks connector is imported lazily, so the other two tools still work
  even if Databricks credentials or the connector package are missing.
- Swap the Frankfurter call in `get_exchange_rate` for any REST API — add an
  `Authorization` header via `httpx` if your API needs a key.
