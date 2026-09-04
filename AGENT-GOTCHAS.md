# Agent gotchas — Hollersports

Environment notes that must not bloat `AGENTS.md`. Keep secrets out.
If a gotcha is fixed, delete the row. Do not leave historical traps as current guidance.
Do not invent rows.

## Local environment

No product-specific traps are recorded yet.

## CI and validators

No product-specific traps are recorded yet.

If a check looks green-but-inert, follow `AGENTS.md` **Escalation**. Do not
patch the test to match the broken path.

## Measurement traps

None recorded. A measurement trap is not a product defect. Do not file one as a bug.

## Do not put here

- Architecture invariants (those stay in `AGENTS.md`)
- Command tables (those stay in `AGENTS.md`)
- Tokens or live credentials
- Invented product behavior
