"""Quick smoke test: call each tool in-process via a FastMCP client."""

import asyncio

from fastmcp import Client

from server import mcp


async def main():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        print("Registered tools:", [t.name for t in tools])

        print("\n-- working_days_between --")
        r = await client.call_tool(
            "working_days_between", {"start": "2026-07-01", "end": "2026-07-15"}
        )
        print(r.data)

        print("\n-- get_exchange_rate --")
        r = await client.call_tool("get_exchange_rate", {"base": "USD", "target": "GBP"})
        print(r.data)

        print("\n(run_sql skipped — needs Databricks credentials)")


if __name__ == "__main__":
    asyncio.run(main())
