# Eval

Experiments and notes on evaluating AI / ML models — measuring performance (P) on a task (T).

## Contents

- [plan.md](plan.md): learning plan for the Claude eval tooling
- [progress.md](progress.md): checklist and running log
- [docs/](docs/): one write-up per phase ([Phase 0: Setup](docs/phase-0-setup.md))

## Setup

```bash
cd eval
uv sync
uv run smoke_test.py                       # uses your Claude Code login, model: haiku
uv run smoke_test.py --model sonnet
uv run smoke_test.py --backend api         # only if you have ANTHROPIC_API_KEY
```

### Model backends

- **`cli` (default):** `common/claude_cli.py` runs `claude -p` with a replaced system prompt, no tools and an empty working directory, so the call is close to a plain API call (about 600 input tokens of overhead). It needs no API key and counts toward your Claude plan's usage. The cost shown is a list-price estimate.
- **`api`:** `common/client.py` uses the Anthropic SDK directly. It needs an `ANTHROPIC_API_KEY` from the Claude Console, which is billed separately from a Claude plan.
