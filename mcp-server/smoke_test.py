"""Smoke test: call every tool in-process via a FastMCP client.

    uv run smoke_test.py
"""

import asyncio
import importlib.util
from pathlib import Path

from fastmcp import Client

# The server file name has hyphens, so load it by path rather than `import`.
_path = Path(__file__).with_name("mcp-local-tools-server.py")
_spec = importlib.util.spec_from_file_location("local_tools_server", _path)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

CALLS = [
    ("add", {"a": 2, "b": 3}),
    ("list_directory", {"path": "."}),
    ("read_text_file", {"path": "pyproject.toml", "max_chars": 80}),
    ("system_info", {}),
    ("roll_dice", {"sides": 6, "count": 3}),
    ("working_days_between", {"start": "2026-07-01", "end": "2026-07-15"}),
    ("get_exchange_rate", {"base": "USD", "target": "GBP"}),  # needs network
]


async def main() -> None:
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        print("Registered tools:", sorted(t.name for t in tools))
        for name, args in CALLS:
            try:
                result = await client.call_tool(name, args)
                print(f"\n-- {name} --\n{result.data!r}")
            except Exception as e:  # keep going so one failure doesn't hide the rest
                print(f"\n-- {name} -- FAILED: {e}")


if __name__ == "__main__":
    asyncio.run(main())
