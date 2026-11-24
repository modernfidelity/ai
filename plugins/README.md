# plugins

Claude Code [plugins](https://code.claude.com/docs/en/plugins): installable bundles of skills, subagents, hooks and MCP servers.

## Start a new plugin

```bash
cp -r plugins/plugin-template plugins/my-plugin
```

Then:

1. In `.claude-plugin/plugin.json`, set `name` (`my-plugin`), `description` and `author`.
2. Replace `skills/hello/` with your own skills (start from [`../skills/skill-template`](../skills/skill-template/)).
3. Edit or delete `agents/` and `hooks/` + `hooks-handlers/`. Every component is optional.

## Layout

```
plugin-template/
├── .claude-plugin/
│   └── plugin.json          required: manifest
├── skills/<name>/SKILL.md   skills (auto-discovered)
├── agents/<name>.md         subagents (auto-discovered)
├── hooks/hooks.json         hook config; ${CLAUDE_PLUGIN_ROOT} = plugin folder
├── hooks-handlers/          scripts the hooks run
└── README.md
```

To add an MCP server, put a `.mcp.json` at the plugin root:

```json
{
  "mcpServers": {
    "my-server": { "command": "uv", "args": ["run", "${CLAUDE_PLUGIN_ROOT}/server.py"] }
  }
}
```

## Test locally

```bash
claude plugin validate plugins/my-plugin            # check the manifest and components
claude --plugin-dir plugins/my-plugin               # load it for one session
claude --plugin-dir plugins                         # load every plugin in this folder
```

## Evaluate it

`claude plugin eval` runs test cases against a plugin and compares with/without it. See Phase 5 of [`../eval/plan.md`](../eval/plan.md).

```bash
claude plugin eval init --bare my-case     # run from inside the plugin folder
```

## Reference scaffold

`claude plugin init <name> --with skills agents hooks mcp` generates the official scaffold, but writes it to `~/.claude/skills/<name>/`, where it loads into every session. This template is based on that scaffold, kept in the repo instead.
