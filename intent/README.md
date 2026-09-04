# Intents

Stage-0 proto-specs for Hollersports. One committed file per change stream.

Canon lives in [`Zero-State-LLC/agent-context`](https://github.com/Zero-State-LLC/agent-context)
(`templates/`, including `templates/sdlc/README.md`). The local blank is
[`_TEMPLATE.md`](_TEMPLATE.md).

This folder holds **blanks and accepted intents only**. Do not invent product work here.

## How to start a change stream

1. Copy [`_TEMPLATE.md`](_TEMPLATE.md) to `intent/<stream>.md`.
2. Fill problem, observable done, locks, non-goals, and labeled claims.
3. Wait for a human to set `Status: accepted`.
4. Then specify (`spec.md` + `## Workflows`). Do not skip to code.

## SDLC order (Zero State)

`intent.md` → constitution (if needed) → specify → plan → tasks → implement → REVIEW / evidence → land.

- FORGE owns plan and tasks.
- Cloud agents implement. No extra bots.
- Human yes on deploy, spend, and legal.

## What stays out

- Product features that no human accepted
- Org status (that is `agent-context` `HANDOFF.md` / `STATUS.md`)
- Secrets, tokens, or live credentials
