# HollerSports System Contract v0.3

Documentation map: [README.md](README.md).

## Product purpose

HollerSports is a **sports betting advisory** system: it observes markets, scores candidates, and helps an operator **decide what they might bet**.

It is **not** a wallet, book, broker, payment rail, or fund mover.

## Money handling

| Claim | Status |
|-------|--------|
| Handles real money | **Never** |
| Places wagers at sportsbooks | **Never** |
| Moves or custodians capital | **Never** |
| Produces advisory candidates + paper simulation | **Yes** |
| Operator may bet elsewhere after reading advice | Human, outside this system |

**No actual money will be handled in this product.** Paper stakes, bankroll figures, ROI, and settlement are **simulation / scoring only** for learning and ranking advice quality.

## Authority

Default mode: **PAPER_ONLY** / **ADVISORY_ONLY** / **CANON-SHADOW**.

## Non-negotiable laws

1. HollerSports must **never execute live capital**, **never place bets**, and **never handle real money**.
2. All market data must pass **source health** before strategies consume it.
3. Strategies may **emit advisory candidates only**; they cannot execute, fund, or promote to live books.
4. Paper “execution” is **simulation only** (shadow ledger for evaluating advice).
5. Dashboard and operator projections are **PROJECTION_ONLY**.
6. Promotion evaluation may **recommend review of advisory quality only**; it cannot authorize live betting or money movement.
7. Settlement requires **outcome provenance** and is used for **advice calibration**, not payout.
8. Same inputs must produce **identical outputs** across 12 deterministic runs (when golden suite is active).
9. Missing provenance, odds, or lines must **fail closed** (`NOT_COMPUTABLE` / `REJECTED`) — never invent certainty.
10. Connecting a real book, payment rail, or capital path requires a **contract rewrite and explicit human approval outside** autonomous control — not a product default.

## Packet flags (v1)

| Flag | Value |
|------|--------|
| `capital_authority` | always `false` |
| `execution_authority` | always `false` |
| Execution `mode` | `PAPER_ONLY` only (simulation of advised tickets) |

## Violation

Any path that moves money, places a live bet, or sets capital/execution authority true is **SYSTEM_FAILURE**.

## Related

- [Repository Atlas](atlas/HOLLERSPORTS_ATLAS.md)
- [Abraxas lineage (concept-only)](ABRAXAS_LINEAGE.md)
- [Production readiness](PRODUCTION_READINESS.md)
- [App Store readiness](APP_STORE_READINESS.md) · [legal/](legal/README.md)
- [Design spec](superpowers/specs/2026-08-04-hollersports-standalone-design.md)
