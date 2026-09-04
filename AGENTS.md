# Agent contract — Hollersports

You are working in **Hollersports** (`Zero-State-LLC/Hollersports`).
This file is the canonical contract for Cursor, Claude, Codex, Grok, and OpenClaw.
Harness adapters (`CLAUDE.md`, optional `CODEX.md`) only point here.

## Intent

Read the active `intent.md` for this change (`intent/`) before editing.
Next stage is `spec.md` — do not skip to code.

If the change is non-trivial and no intent exists, draft from
[`intent/_TEMPLATE.md`](intent/_TEMPLATE.md) and wait for a human to accept it.
Do not invent a product intent.

## Commands

Documented in [`README.md`](README.md). Do not invent commands.

| Task | Command |
|---|---|
| Run engine tests | `python -m pytest tests/ -v` |
| Run engine tests with coverage | `python -m pytest tests/ --cov=engine --cov-report=html` |
| Run usage example | `python examples/basic_usage.py` |

## Invariants

From this repo's existing README / contributing rules. Do not invent new product behavior.

- No slate leakage: each slate is processed independently.
- Determinism: same inputs produce the same outputs.
- Provenance: keep a full audit trail of transformations.
- ABX-Core compliance: no mock placeholders; explicit semantics.
- Do not put secrets, tokens, or live credentials in the tree.
- Authorized Zero State contributors and agents only (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

## Graft and docs

This repo has no `graft/`. Start at [`README.md`](README.md) and
[`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md). Do not copy a code map here.

## Escalation

If CI, tests, or validators look wrong — missing coverage, silent skips,
green-but-inert checks, or a suite that contradicts documented behavior:

1. Open a defect issue with label `type:bug`.
2. Do **not** patch tests, fixtures, or CI to force green.
3. Do **not** weaken an assertion to match a broken implementation.

A red honest check is better than a green lie.

## Environment gotchas

Long environment notes live in [`AGENT-GOTCHAS.md`](AGENT-GOTCHAS.md).
Keep them out of this file.

## Team context

Org and partner status is not this repo. Load `Zero-State-LLC/agent-context`:

1. `HANDOFF.md`
2. `STATUS.md`
3. `DECISIONS.md` only if a prior choice affects this task

Clone: `gh repo clone Zero-State-LLC/agent-context ~/agent-context`.
Pull `--ff-only` before trusting a local copy.

Canon for this pack: `agent-context` `templates/` (intent is SDLC stage-0).

## Skills

Name only skills that already exist. Do not invent skills or bots.
No `spec.md` `## Workflows` yet. Defaults: `anti-slop-code`,
`production-systems`, `google-developer-style`. Reuse existing Actions;
do not invent bots.

## Size

Keep this file short (about 80 lines; hard ceiling 12 KB).
Move procedure and gotchas out, not in.
