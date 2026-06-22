from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather is sunny in {city}."


model = ChatOllama(model="gemma4:latest")
agent = create_agent(model, [get_weather])

result = agent.invoke({
    "messages": [("user", "What's the weather in Tokyo?")]
})

print(result["messages"][-1].content)
