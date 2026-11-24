# mcp-server

A minimal [FastMCP](https://gofastmcp.com) server exposing example tools
that Claude Code can call locally over stdio (or HTTP).

| Tool | Type | What it does |
|------|------|--------------|
| `add` | Pure Python | Adds two numbers |
| `roll_dice` | Pure Python | Rolls `count` dice with `sides` faces |
| `working_days_between` | Pure Python | Counts Mon–Fri days between two ISO dates |
| `list_directory` | Local filesystem | Lists a directory's contents |
| `read_text_file` | Local filesystem | Reads a text file, truncated to `max_chars` |
| `system_info` | Local machine | OS, release, architecture, Python version |
| `get_exchange_rate` | Third-party REST API | Latest FX rate from the free [Frankfurter API](https://frankfurter.dev) (no key needed) |

## Setup

Requires [uv](https://docs.astral.sh/uv/). Dependencies are declared in
`pyproject.toml` and get installed automatically the first time you run
the project.

```bash
cd mcp-server
uv sync
```

## Run standalone (optional, for testing)

```bash
uv run mcp-local-tools-server.py          # stdio
uv run mcp-local-tools-server.py --http   # HTTP on http://127.0.0.1:8000
```

Over stdio it sits waiting for MCP messages. That's expected: it's meant
to be launched by an MCP client, not used interactively.

## Test

```bash
uv run smoke_test.py   # calls every tool in-process; get_exchange_rate needs network
```

## Register with Claude Code

From inside this folder, run:

```bash
claude mcp add local-tools -- uv run --project "$(pwd)" "$(pwd)/mcp-local-tools-server.py"
```

Then start/restart Claude Code and the tools will be available.

By default this registers the server at **local** scope, meaning it's
only usable from the directory you ran the command in (stored in
`~/.claude.json` under that project). Pass `-s user` instead to make it
available in every project, or `-s project` to check it into this repo's
`.mcp.json` and share it with anyone who clones it:

```bash
claude mcp add -s user local-tools -- uv run --project "$(pwd)" "$(pwd)/mcp-local-tools-server.py"
```

Useful follow-ups:

```bash
claude mcp list              # confirm it's registered
claude mcp get local-tools   # show its config
claude mcp remove local-tools # unregister it
```

Inside a Claude Code session, run `/mcp` to check connection status and
see the tools it exposes.

## Adding your own tools

Add a new function to `mcp-local-tools-server.py` decorated with
`@mcp.tool`, e.g.:

```python
@mcp.tool
def my_tool(x: int) -> int:
    """One-line description shown to the model."""
    return x * 2
```

Type hints and the docstring are what the model sees, so keep both
accurate.
