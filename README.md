# AI Sandbox

A personal sandbox for hands-on experiments with AI and machine learning: evaluating models, building agents and tool calling, running MCP servers, neural network notebooks and computer vision.

## Projects

Each folder is a self-contained experiment.

| Folder | What it is | Stack |
|---|---|---|
| [`eval/`](eval/) | Learning Claude eval tooling: a phased [plan](eval/plan.md), [progress tracker](eval/progress.md) and per-phase [write-ups](eval/docs/) | Python, `uv`, Anthropic SDK, `claude -p` |
| [`local_ai/`](local_ai/) | Tool-calling agent experiments with local models (Ollama / Gemma) and Claude | Python, `uv`, LangChain, LangGraph, Ollama |
| [`mcp-server/`](mcp-server/) | Local MCP server for Claude Code with 7 example tools: pure Python, local filesystem/system info and a third-party REST API (FX rates) | Python, `uv`, FastMCP |
| [`notebooks/`](notebooks/) | Jupyter notebooks covering tensors, perceptrons, MLPs, neural networks and object detection | PyTorch, torchvision |
| [`vision/`](vision/) | Computer vision experiments: RegNet image classification (pretrained and from scratch) | PyTorch, torchvision |
| [`openai_symfony/`](openai_symfony/) | Symphony: a coding-agent orchestrator that polls Linear issues and runs Codex agents in isolated workspaces | Python, asyncio, aiohttp, pytest |

## Getting started

Python projects are set up independently. From inside a project folder:

```bash
uv sync                            # projects with a pyproject.toml
pip install -r requirements.txt    # projects with only a requirements.txt
```

Where a folder has a README, it explains how to run that project.
