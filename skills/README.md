# skills

Claude Code [skills](https://code.claude.com/docs/en/skills): folders of instructions (plus optional reference files and scripts) that Claude loads when a request matches the skill's `description`.

## Start a new skill

```bash
cp -r skills/skill-template skills/my-skill
```

Then edit `skills/my-skill/SKILL.md`:

1. Set `name:` to match the folder name (`my-skill`).
2. Rewrite `description:`. It's the most important line, because Claude decides whether to use the skill from it alone.
3. Fill in the steps, and delete anything you don't need (`reference.md`, `scripts/`).

## Layout

```
skill-template/
├── SKILL.md        required: frontmatter (name, description) + instructions
├── reference.md    optional: detail loaded only when needed
└── scripts/        optional: helpers Claude can run
    └── example.py
```

## Use a skill

Skills in this folder aren't loaded automatically. Either:

- **Personal (all projects):** copy it to `~/.claude/skills/my-skill/`
- **One project:** copy it to `<project>/.claude/skills/my-skill/`
- **Share it:** bundle it into a plugin (see [`../plugins/`](../plugins/))

## Check it

```bash
claude plugin validate skills/my-skill
```

## Tips

- Keep `SKILL.md` short and move long material to `reference.md`.
- Write the description in terms of what users say, not what the skill is.
- Test the trigger by asking Claude something the description should match, then something it shouldn't.
