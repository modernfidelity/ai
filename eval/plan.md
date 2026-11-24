# Eval Learning Plan — Claude Eval Tooling

## Goal

Learn how to measure whether a Claude-powered thing is getting better or worse. Do this hands-on with the Claude eval tools, using code that's already in this repo as the thing being tested.

> An eval is a fixed set of **inputs** (tasks, T), a **grader** that scores each output (P), and a **harness** that runs them repeatedly so you can compare two versions: a prompt, a model, a tool set.

## Tools in scope

| Tool | What it evaluates | How you drive it |
|---|---|---|
| **Anthropic Python SDK + a hand-rolled harness** | A prompt / model / agent called through the Messages API | Python script: cases → `client.messages.create` → graders → scores |
| **`/claude-api build-eval`** (Claude Code skill) | Same as above. Interviews you to source inputs and pick graders, then writes a runnable script with measured cost | Run inside Claude Code |
| **`/claude-api hillclimb`** | Iteratively improves a prompt against an existing eval with a train/validation/test split | Run inside Claude Code once an eval exists |
| **Eval audit checklist** (`eval-audit` guide in the claude-api skill) | Whether an eval itself can be trusted: task design, harness, metrics, graders, sensitivity | Ask Claude Code "is my eval any good?" |
| **`claude plugin eval`** (CLI) | A Claude Code plugin, skill, or MCP server: does Claude use it correctly, and does it help compared with no plugin? | `claude plugin eval init`, `case.yaml` / `prompt.md` + `graders/*.md`, `--ablation with-without`, `--runs`, `--threshold`, HTML report |

## Core concepts to learn (apply throughout)

- **Cases**: representative inputs, plus edge cases and adversarial ones. Aim for quality over quantity.
- **Graders**, cheapest first:
  1. **Code-based**: exact match, regex, JSON schema, "did it call tool X with args Y"
  2. **LLM-as-judge**: a rubric scored by a cheaper model (e.g. `claude-haiku-5-5`). Validate it against hand labels.
  3. **Human review**: the gold standard for spot checks.
- **Variance**: LLM output is non-deterministic, so run each case N times and report the mean and spread.
- **Baseline and ablation**: always compare against something, e.g. the previous prompt, another model, or no plugin.
- **Train/test split**: don't tune against the cases you report on.
- **Cost**: measure the cost per run before scaling up. Use Message Batches (50% cheaper) for bulk runs.

## Phases

### Phase 0: Setup
- Create a `uv` project in `eval/` with the `anthropic` SDK
- Confirm credentials. Done via the Claude Code login (`claude -p` backend), since there's no API key; see [docs/phase-0-setup.md](docs/phase-0-setup.md)
- Write a one-call smoke test

### Phase 1: First eval by hand (API, code-graded)
- **Target:** a small single-call task, e.g. sentiment classification or extraction. This ties back to the "Sentiment Analysis" item in the root README.
- 15–20 hand-written cases with expected labels, stored in `cases.jsonl`
- Exact-match grader; run each case 3 times; print accuracy and a per-case table
- Compare two prompts and two models (e.g. `claude-haiku-5-5` vs `claude-opus-5-5`)
- **Learn:** the harness shape, variance, cost per run

### Phase 2: LLM-as-judge
- **Target:** an open-ended task such as summarisation, where exact match doesn't work
- Write a rubric with 3–5 independently gradeable criteria and a structured-output judge
- Hand-label about 10 outputs and measure how often the judge agrees with you
- **Learn:** judge bias, why a rubric beats asking for a 1–10 score, and how to calibrate the judge

### Phase 3: Use the Claude Code eval skills
- Run `/claude-api build-eval` on the Phase 1/2 task and compare its output with the hand-built harness
- Run the eval audit checklist against your Phase 1 eval and fix what it flags
- Run `/claude-api hillclimb` with a small budget, keeping the test split as the headline number
- **Learn:** what a disciplined eval workflow adds on top of a quick script

### Phase 4: Agent / tool-use evals
- **Target:** `local_ai/claude_agent.py` (LangChain + Claude + `my_tools`)
- Cases are user requests; graders check whether the right tool was called, whether the arguments were valid, and whether the final answer is correct
- Track tool-call count and turns as efficiency metrics
- **Learn:** trajectory vs outcome grading, and multi-turn non-determinism

### Phase 5: `claude plugin eval`
- **Target:** `mcp-server/mcp-local-tools-server.py`, packaged as a Claude Code plugin
- `claude plugin eval init` to scaffold an `evals/` suite, with cases like "roll 3d6", "list files in X", "add these numbers"
- Graders: `tool_used` checks plus LLM graders on the answer
- Run with `--ablation with-without` to see whether the plugin actually helps, and use `--runs`, `--threshold`, `--max-cost-usd`
- Read the HTML report
- **Learn:** evaluating tools/skills rather than prompts, mocks for MCP servers, and CI gating

### Phase 6: Wrap-up
- Write `notes.md` covering what each tool is good for, when to use which, and the pitfalls hit
- Optional: add a CI job that runs the plugin eval with `--threshold`

## Proposed folder layout

```
eval/
├── README.md
├── plan.md             ← this file
├── progress.md         ← running log + checklist
├── docs/               one write-up per phase (phase-0-setup.md, …)
├── pyproject.toml      (Phase 0)
├── common/             shared harness helpers (claude_cli + API backends, runner, scoring)
├── 01-classification/  cases.jsonl, run.py, results/
├── 02-llm-judge/       cases.jsonl, rubric.md, judge.py, results/
├── 03-skills/          output of build-eval / hillclimb
├── 04-agent/           agent tool-use eval
└── 05-plugin-eval/     plugin wrapper + evals/ for claude plugin eval
```

## Guardrails

- Every run spends real money, so set the case count × runs × model before running and use `--max-cost-usd` where it's available
- Keep `results/` out of git, or commit only summary files
- Never put API keys in the repo
