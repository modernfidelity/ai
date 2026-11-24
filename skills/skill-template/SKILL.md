---
name: skill-template
description: TODO: say WHEN Claude should use this skill, in one or two sentences. Include the phrases a user might actually type ("summarise this PR", "set up a new X"). Claude matches requests against this text, so be specific.
---

# Skill template

TODO: one paragraph saying what this skill does and what it produces.

## When to use

- TODO: situation 1
- TODO: situation 2

Don't use it for: TODO (say what's out of scope, so the skill doesn't trigger on near-misses).

## Steps

1. TODO: first thing Claude should do (gather input, read a file, ask a question)
2. TODO: the main work
3. TODO: how to check the result
4. TODO: what to hand back to the user, and in what format

## Resources

- `reference.md`: longer background material. Claude reads it only when a step needs it, so keep this file short and put detail there.
- `scripts/`: helper scripts Claude can run, e.g. `python3 scripts/example.py <arg>`.

## Example

**User:** TODO: an example request
**Result:** TODO: what a good outcome looks like
