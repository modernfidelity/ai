# Progress

Tracks work against [plan.md](plan.md). Newest log entries go at the top.

**Current status:** Phase 0 ✅ complete → Phase 1 next (waiting on the task choice)

| Phase | Status | Write-up |
|---|---|---|
| 0: Setup | ✅ Complete (2026-11-24) | [docs/phase-0-setup.md](docs/phase-0-setup.md) |
| 1: First eval by hand | ⏳ Next | |
| 2: LLM-as-judge | Not started | |
| 3: Claude Code eval skills | Not started | |
| 4: Agent / tool-use evals | Not started | |
| 5: `claude plugin eval` | Not started | |
| 6: Wrap-up | Not started | |

## Checklist

### Phase 0: Setup ✅
- [x] Create `eval/` folder, `plan.md`, `progress.md`
- [x] `uv` project + `anthropic` SDK (`uv sync`)
- [x] Credentials: no API key, so the default backend uses the Claude Code login (`claude -p`); the API backend is kept for later
- [x] Smoke test passes (`uv run smoke_test.py`, claude-haiku-5-5, ~640 tokens in, ~$0.0001 list)
- [x] Phase 0 documented in [docs/phase-0-setup.md](docs/phase-0-setup.md)

### Phase 1: First eval by hand (code-graded)
- [ ] Pick task + write 15–20 cases
- [ ] Harness: run × 3, exact-match grader, per-case table
- [ ] Compare 2 prompts
- [ ] Compare 2 models
- [ ] Record cost per full run

### Phase 2: LLM-as-judge
- [ ] Rubric (3–5 criteria)
- [ ] Judge with structured output
- [ ] Hand-label ~10 outputs, measure agreement

### Phase 3: Claude Code eval skills
- [ ] `/claude-api build-eval`
- [ ] Eval audit on the Phase 1 eval
- [ ] `/claude-api hillclimb` (small budget)

### Phase 4: Agent / tool-use evals
- [ ] Cases for `local_ai/claude_agent.py`
- [ ] Tool-choice + argument + outcome graders
- [ ] Efficiency metrics (tool calls, turns)

### Phase 5: `claude plugin eval`
- [ ] Package `mcp-server` as a plugin
- [ ] `claude plugin eval init`
- [ ] Run with ablation, read the HTML report
- [ ] Try `--threshold` / `--max-cost-usd`

### Phase 6: Wrap-up
- [ ] `notes.md`: when to use which tool
- [ ] (Optional) CI job

## Log

### 2026-11-24 (Phase 0 complete)
- Built the project: `pyproject.toml`, `uv.lock`, `.gitignore`, `common/client.py` (SDK backend + pricing), `common/claude_cli.py` (`claude -p` backend), `smoke_test.py`.
- Environment: Python 3.14.3, `anthropic` 2.13.0, managed by `uv` (started on venv + pip, then switched once uv was installed).
- No Anthropic API key, so the default backend is the Claude Code login via `claude -p`. Its system prompt is replaced, tools are off, it runs from an empty working directory and saves no sessions, which cuts overhead from about 13k to about 600 input tokens. `--effort` is wired in, and `--json-schema` is available for Phase 2.
- Decision: no server-side refusal fallbacks in the harness, because a silent model switch would contaminate comparisons.
- Smoke test passes: claude-haiku-5-5, ~640 tokens in, ~$0.0001 list.
- Open issue: an intermittent ~15k input-token spike on some `claude -p` calls (2 of ~10). The Phase 1 harness will log per-call tokens and flag outliers.
- Write-up: [docs/phase-0-setup.md](docs/phase-0-setup.md).

### 2026-11-24
- Created `eval/` with README, plan, and progress tracker.
- Confirmed `claude plugin eval` is available locally (supports `init`, ablation, mocks, HTML reports).

## Open questions
- Cause of the intermittent ~15k token spike on `claude -p` (see Phase 0 known issues)
- Which task for Phase 1: sentiment classification or something else?
- Should results be committed (summaries only) or fully gitignored?
