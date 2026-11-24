# Phase 0: Setup

**Status:** Complete (2026-11-24)
**Goal:** a reproducible Python project that can make a model call and report its tokens and cost, which every later eval builds on.

## What was built

```
eval/
├── pyproject.toml        project + dependency (anthropic SDK)
├── uv.lock               pinned dependency versions
├── .gitignore            ignores results/ and .env
├── smoke_test.py         one call → reply, tokens, cost
└── common/
    ├── claude_cli.py     backend: headless Claude Code (`claude -p`), the default
    └── client.py         backend: Anthropic SDK (needs an API key), plus pricing table
```

Environment: Python 3.14.3, `anthropic` 2.13.0, managed by `uv`.

## How to run

```bash
cd eval
uv sync                                   # create .venv from uv.lock
uv run smoke_test.py                      # default: cli backend, haiku
uv run smoke_test.py --model sonnet       # haiku | sonnet | opus | full model id
uv run smoke_test.py --backend api        # Anthropic SDK; needs ANTHROPIC_API_KEY
```

Expected output:

```
backend:     claude -p (Claude Code login)
model:       claude-haiku-5-5
stop_reason: end_turn
reply:       eval smoke test OK
tokens:      in=640 out=10
cost (list): $0.000133  (1034 ms)
```

## Model backends

There is no Anthropic API key, so Phase 0 added a second way to call Claude.

| | `cli` (default) | `api` |
|---|---|---|
| Module | `common/claude_cli.py` → `complete()` | `common/client.py` → `get_client()` |
| Auth | Claude Code login (Claude plan) | `ANTHROPIC_API_KEY` from the Claude Console |
| Billing | Counts toward plan usage limits; the cost shown is a list-price estimate | Pay-per-token |
| Overhead | ~630 input tokens per call | None beyond your prompt |
| Controls | model, system prompt, `--effort`, `--json-schema` | Full Messages API (`max_tokens`, effort, structured outputs, batches, …) |
| Speed | ~1 s per call (process start-up) | Faster; can run concurrently and in batches |

### How the `cli` backend keeps calls clean

Running `claude -p` normally sends Claude Code's own system prompt (~13k tokens) and its tool definitions, which would distort an eval. `complete()` strips that out:

| Flag / setting | Why |
|---|---|
| `--system-prompt "<yours>"` | Replaces Claude Code's system prompt |
| `--tools ""` | No built-in tools, so the model just answers |
| `cwd` = fresh empty temp dir | No project `CLAUDE.md` or settings get picked up |
| `--no-session-persistence` | Eval calls don't clutter session history |
| `--output-format json` | Gives the reply, usage, cost and duration as JSON |

Measured effect: about **13k → about 600** input tokens per call.

## Decisions

- **Claude Code login as the default backend.** It unblocks the plan without an API key. It's close enough to a raw API call for Phases 1–2. Switch to the `api` backend if a phase needs `max_tokens`, batches or high concurrency.
- **No server-side refusal fallbacks in the harness.** Fallbacks silently retry on a different model. In an eval that mixes two models' results under one label, so refusals are reported as they happen instead.
- **`uv` over pip.** It matches `local_ai/` and `mcp-server/`, and gives a lockfile for reproducible runs.
- **Raw results are gitignored** (`results/`). Summaries get committed deliberately.

## What I learned

- An eval harness needs a **cost per call** from day one, because later phases multiply it: cases × runs × models × prompts.
- Tools that wrap a model (like Claude Code) add their own context. Before trusting a tool as an eval backend, **measure its overhead**.
- `claude -p --output-format json` reports `total_cost_usd`, per-model usage and `duration_ms`, which covers most of what a harness needs.

## Known issues

- **Intermittent token spike:** 2 of about 10 `claude -p` calls reported about 15k input tokens instead of about 630, and the replies were still correct. It isn't caused by `--effort` and didn't reproduce in a loop. The cause is unknown, possibly a cold start in a new temp dir. **Mitigation:** the Phase 1 harness logs tokens per call and flags outliers, so they don't skew cost or token comparisons.

## Next: Phase 1

A hand-built, code-graded eval: about 15–20 cases, each run 3 times, scored by exact match, comparing two prompts and two models. See [plan.md](../plan.md).
