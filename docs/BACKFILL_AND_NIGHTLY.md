# Backfill and nightly advice-quality jobs

Advisory only — **no real money**, **no book placement**.

## Hermes / agents — start here

| | |
|--|--|
| **Playbook** | [`docs/agents/HERMES_BACKFILL.md`](agents/HERMES_BACKFILL.md) |
| **What needs backfill?** | `make backfill-status` or `python scripts/backfill_status.py` |
| **Run backfill** | `make backfill` |
| **V0.6 read-only audit** | `make v06-backfill-audit` |
| **Fixture list** | [`fixtures/MANIFEST.json`](../fixtures/MANIFEST.json) |
| **Repo agent entry** | [`AGENTS.md`](../AGENTS.md) |

Status JSON includes `needs_backfill`, `current_sample`, `target_sample`, and `suggested_command`.

Before importing historical data into the V0.6 domains, run:

```bash
make v06-backfill-audit
# strict automation gate; exits 1 until temporal V0.6 evidence is joinable
python scripts/audit_v06_backfill.py --assert-v06-ready
```

The V0.6 auditor is read-only. It inventories market memory, settlements, prop,
context, and dependency packets; validates required provenance; checks event joins
and settlement ordering; and reports blockers without creating data directories.
Existing V0.5 fixture backfill remains a separate PAPER_ONLY control workflow.

## Purpose

Accumulate settled paper simulations so reliability buckets and promotion review
have sample size. This is **advice calibration**, not P&L.

## Fixture backfill (offline / CI-safe)

```bash
cd Hollersports
python3 -m venv .venv && source .venv/bin/activate
pip install -e "packages/hollersports[dev]"

# Repeatable operator day → smoke receipt
python scripts/smoke_operator_day.py --out docs/evidence/smoke_operator_day.last.json

# Discover gaps then accumulate into shared calibration bank
make backfill-status
make backfill
# or: python scripts/backfill_fixtures.py --repeats 4 --paper-top-n 50 \
#        --data-root data/backfill --out docs/evidence/backfill_calibration.last.json

# Or API (single day; appends to HOLLER_DATA_ROOT ledgers)
# make api  then: curl -X POST localhost:8000/v1/runs/full-day -H 'content-type: application/json' -d '{"fixture":"day001"}'
```

Backfill writes:

- `data/backfill/ledgers/settlements_history.jsonl` — cumulative settled outcomes  
- `data/backfill/ledgers/reliability.jsonl` — reliability snapshots  
- calibration ladder receipt with `sample_size` / `status` / `model_edge_allowed`

## Calibration bank + re-settles

The bank is **append-only** (`data/backfill/ledgers/settlements_history.jsonl`).
Re-settling the same paper ticket (PENDING → WIN, or ESPN re-fetch) appends a new
row. Calibration and `backfill_status` count **latest status per `entry_id`** so
tickets are not double-counted.

## Optional live free-first observation

```bash
# ESPN only (observe pack only)
python scripts/holler_free_first_ingest.py --espn-only --out out/free_first.json

# ESPN + Odds API
export THE_ODDS_API_KEY=...
python scripts/holler_free_first_ingest.py --out out/free_first.json
```

Workbench: **Free-first live observe** on Today (may hit network; fail-closed if offline).

## Free-first closed day (observe → compete → paper → settle → bank)

Prefer **injected** JSON for CI; live finals are opt-in.

```bash
# CI-safe (no network)
python scripts/free_first_operator_day.py \
  --espn-raw path/to/espn.json --odds-raw path/to/odds.json \
  --settle-espn-raw path/to/finals.json --leagues NBA \
  --data-root data/backfill --out docs/evidence/free_first_day.last.json

# Live finals into the same bank (network; never places bets)
make free-first-day
# or: python scripts/free_first_operator_day.py --leagues NBA --fetch-espn-finals \
#        --data-root data/backfill --out docs/evidence/free_first_day.last.json
```

Non-final ESPN outcomes stay PENDING and are collapsed out of the calibration
sample until a later terminal re-settle.

## Suggested cron (operator machine)

```cron
# Nightly fixture sim (always offline-safe)
15 6 * * * cd /path/to/Hollersports && . .venv/bin/activate && python scripts/smoke_operator_day.py --out docs/evidence/smoke_operator_day.last.json >> out/nightly.log 2>&1

# Optional: live observe weekdays (requires network; never places bets)
30 6 * * 1-5 cd /path/to/Hollersports && . .venv/bin/activate && python scripts/holler_free_first_ingest.py --espn-only --out out/free_first_$(date +\%Y\%m\%d).json >> out/nightly.log 2>&1

# Optional: closed free-first day weekdays → calibration bank (network; advisory only)
45 6 * * 1-5 cd /path/to/Hollersports && . .venv/bin/activate && python scripts/free_first_operator_day.py --leagues NBA --fetch-espn-finals --data-root data/backfill --out out/free_first_day_$(date +\%Y\%m\%d).json >> out/nightly.log 2>&1
```

## Reliability review

After settlements exist in the API store:

```bash
curl -s localhost:8000/v1/reliability | jq .
# Append-only snapshots after each settle
curl -s 'localhost:8000/v1/reliability?history=1&limit=20' | jq .
```

Or open Workbench **Health → Advice reliability** and **Reliability history**.

Promotion stays **BLOCKED** until design gates (sample size, ROI, etc.) pass — still
**review only**, never money.

## Hard rules

- Do not schedule any script that places bets or moves capital (none exist).
- Do not commit API keys.
- Prefer fixtures for CI and demos.
