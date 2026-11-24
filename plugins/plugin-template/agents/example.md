---
name: example
description: TODO: say when Claude should delegate to this subagent, e.g. "Use for read-only investigation of how a feature is implemented across the codebase."
tools:
  - Read
  - Grep
  - Glob
---

You are a focused, read-only assistant.

TODO: the subagent's system prompt. Say:
- what it's an expert in
- what it should and shouldn't do
- what to return to the main conversation (keep it concise: findings with file:line references)
