# mcp-server

A minimal [FastMCP](https://gofastmcp.com) server exposing a few example
tools (`add`, `list_directory`, `read_text_file`, `system_info`,
`roll_dice`) that Claude Code can call locally over stdio.

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
uv run mcp-local-tools-server.py
```

It will sit waiting for MCP messages on stdio — that's expected, it's
meant to be launched by an MCP client, not used interactively.

## Register with Claude Code

From any directory, run:

```bash
claude mcp add local-tools -- uv run --project /path/to/ai/mcp-server /path/to/ai/mcp-server/mcp-local-tools-server.py
```

Then start/restart Claude Code and the tools will be available.

By default this registers the server at **local** scope, meaning it's
only usable from the directory you ran the command in (stored in
`~/.claude.json` under that project). Pass `-s user` instead to make it
available in every project, or `-s project` to check it into this repo's
`.mcp.json` and share it with anyone who clones it:

```bash
claude mcp add -s user local-tools -- uv run --project /path/to/ai/mcp-server /path/to/ai/mcp-server/server.py
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
