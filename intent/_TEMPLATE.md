# Intent — {{CHANGE_STREAM}}

Author: {{AUTHOR}}
Date: {{DATE}}
Status: draft | accepted | superseded
Product: Hollersports (`Zero-State-LLC/Hollersports`)

This file is a proto-spec. It comes **before** specify.
Next stage is `spec.md` (spec-kit specify). Do not skip to code.

One committed intent per change stream. Live under `intent/`.
Copy this blank. Do not invent product work in the template.

Canon: `Zero-State-LLC/agent-context` (`templates/intent.md.template`).

## Problem / why now

{{PROBLEM}}

[verified: {{EVIDENCE}}] or [assumed: {{REASON}}]

## Proposed outcome

Observable done (a stranger can check this without reading the chat):

- {{OUTCOME_1}}
- {{OUTCOME_2}}

## Affected users / systems

- Users: {{USERS}}
- Systems: {{SYSTEMS}}

## Constraints

Product-true locks (do not reopen in implement):

- {{LOCK_1}}

Non-goals:

- {{NON_GOAL_1}}

## Open questions

- {{QUESTION_1}}

## Claims

Label every non-obvious claim. Prefer a table when there are several.

| Claim | Label |
|---|---|
| {{CLAIM}} | `[verified: {{EVIDENCE}}]` or `[assumed: {{REASON}}]` |

## Next

A human accepts this file (`Status: accepted`). Then specify
(`spec.md` + `## Workflows`). Do not implement from this file alone.
