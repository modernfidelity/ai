# AI Sandbox

A personal sandbox for hands-on experiments with AI and machine learning: evaluating models, building agents and tool calling, running MCP servers, neural network notebooks and computer vision.

## Projects

Each folder is a self-contained experiment.

| Folder | What it is | Stack |
|---|---|---|
| [`eval/`](eval/) | Learning Claude eval tooling: a phased [plan](eval/plan.md), [progress tracker](eval/progress.md) and per-phase [write-ups](eval/docs/) | Python, `uv`, Anthropic SDK, `claude -p` |
| [`local_ai/`](local_ai/) | Tool-calling agent experiments with local models (Ollama / Gemma) and Claude | Python, `uv`, LangChain, LangGraph, Ollama |
| [`mcp-server/`](mcp-server/) | Minimal MCP server with example local tools (`add`, `list_directory`, `read_text_file`, `system_info`, `roll_dice`) for Claude Code | Python, `uv`, FastMCP |
| [`tools/mcp-server/`](tools/mcp-server/) | Example MCP server showing three tool patterns: Databricks SQL, a pure-Python function and a third-party REST API | Python, `uv`, FastMCP |
| [`notebooks/`](notebooks/) | Jupyter notebooks covering tensors, perceptrons, MLPs, neural networks and object detection | PyTorch, torchvision |
| [`vision/`](vision/) | Computer vision experiments: RegNet image classification (pretrained and from scratch) | PyTorch, torchvision |
| [`openai_symfony/`](openai_symfony/) | OpenAI Symfony and Claude Code experiments (`symfony/`, `symfony-python/`) | Python |

## Getting started

Python projects are set up independently. From inside a project folder:

```bash
uv sync                            # projects with a pyproject.toml
pip install -r requirements.txt    # projects with only a requirements.txt
```

Where a folder has a README, it explains how to run that project.
