# openai_symfony

A Python implementation of **Symphony**, a coding-agent orchestration service, built with Claude Code. The package lives in [`symfony-python/`](symfony-python/).

## How it works

- Reads a `WORKFLOW.md` file (YAML front matter for config + a Jinja2 prompt template) and hot-reloads it on change
- Polls a [Linear](https://linear.app) project for issues (`LINEAR_API_KEY`)
- For each issue, creates an isolated workspace and runs a coding agent through `codex app-server`
- Optional HTTP status server (`--port`)

> **Trust posture:** the agent auto-approves its actions and assumes a high-trust environment. Only run it against repos and trackers you control.

## Setup

```bash
cd openai_symfony/symfony-python
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

## Run

```bash
export LINEAR_API_KEY=...
.venv/bin/symphony path/to/WORKFLOW.md --port 8080
```

## Test

```bash
.venv/bin/pytest
```
