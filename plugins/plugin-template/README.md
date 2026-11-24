# plugin-template

A starting-point Claude Code plugin.

| Component | Path | Purpose |
|---|---|---|
| Manifest | `.claude-plugin/plugin.json` | Name, version, description, author |
| Skill | `skills/hello/SKILL.md` | Minimal working skill ("hello plugin") |
| Subagent | `agents/example.md` | Read-only subagent to customise |
| Hook | `hooks/hooks.json` → `hooks-handlers/session_start.py` | Runs on session start; currently a no-op |

## Try it

```bash
claude --plugin-dir plugins/plugin-template
```

Then ask "hello plugin".

Replace `skills/hello/` with your own skills. [`skills/skill-template`](../../skills/skill-template/) at the repo root is a good starting point.
