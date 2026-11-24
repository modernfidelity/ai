import inspect
import os

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool

import my_tools


def load_tools(module):
    """Wrap all functions defined in a module as LangChain tools."""
    tools = []
    for _, fn in inspect.getmembers(module, inspect.isfunction):
        if fn.__module__ == module.__name__:
            tools.append(tool(fn))
    return tools


def start_instance(model_name="claude-sonnet-5-5"):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY before running claude_agent.py")

    tools = load_tools(my_tools)
    # Sonnet 5.5 thinks adaptively by default and thinking counts toward
    # max_tokens, so allow more than LangChain's 4096 default.
    model = ChatAnthropic(model=model_name, max_tokens=16000)
    agent = create_agent(model, tools)

    print("=" * 50)
    print("Claude agent initialized.")
    print(f"Model: {model_name}")
    print(f"Loaded tools: {[t.name for t in tools]}")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 50)

    messages = []
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Shutting down agent.")
            break
        if not user_input:
            continue

        messages.append(("user", user_input))
        result = agent.invoke({"messages": messages})
        messages = result["messages"]
        print(f"\nClaude: {messages[-1].content}")


if __name__ == "__main__":
    start_instance()
