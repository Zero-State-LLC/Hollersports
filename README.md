<div align="center">

<img src="docs/images/hollersports-hero.jpg" alt="HollerSports — paper-only sports market intelligence operator hero" width="100%" />

# HollerSports

> **Betting advisory only** — no wallets, no book placement, **no real money**.\
> Free-first / fixture ingest → market-first candidates → paper simulation for ranking advice — fail-closed and deterministic.

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Package](https://img.shields.io/badge/hollersports-0.5.0-0B3D91)](packages/hollersports/pyproject.toml)
[![Freeze](https://img.shields.io/badge/freeze-v0.5.0--advisory--beta-blue)](docs/TRACK_F_FREEZE_AND_FIELD_TEST.md)
[![Purpose](https://img.shields.io/badge/purpose-advise%20only-0B3D91)](docs/SYSTEM_CONTRACT.md)
[![Money](https://img.shields.io/badge/real%20money-never-success)](docs/SYSTEM_CONTRACT.md)
[![Mode](https://img.shields.io/badge/mode-PAPER%20SIM-blue)](docs/SYSTEM_CONTRACT.md)
[![Books](https://img.shields.io/badge/live%20books-disabled-red)](docs/SYSTEM_CONTRACT.md)
[![Abraxas](https://img.shields.io/badge/Abraxas-concept%20lineage%20only-lightgrey)](docs/ABRAXAS_LINEAGE.md)
[![Advisory beta](https://img.shields.io/badge/local%20advisory%20beta-PASS-blue)](docs/PRODUCTION_READINESS.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-informational)](LICENSE)

[Quick start](#quick-start) ·
[Docs index](docs/README.md) ·
[Atlas](docs/atlas/HOLLERSPORTS_ATLAS.md) ·
[Field test](docs/TRACK_F_FREEZE_AND_FIELD_TEST.md) ·
[Agents](AGENTS.md) ·
[Release notes](docs/RELEASE_NOTES.md) ·
[System contract](docs/SYSTEM_CONTRACT.md)

</div>

---

## Why

Most “betting tools” either invent certainty or quietly become money rails. HollerSports does neither:

1. **Observe** markets with provenance and source health.
2. **Advise** with scored candidates (`SHADOW_ONLY`) — what you *might* consider betting.
3. **Simulate** advised tickets on paper to measure advice quality — **not** to move money.
4. **Fail closed** when odds, lines, or provenance are missing.

> Strategies advise. Guards keep it paper. Ledgers score the advice. Humans decide — and bet elsewhere, if at all.

**No actual money is handled.** Bankroll / stake / ROI fields are simulation metrics for ranking and calibration.

## Status

| | |
|--|--|
| **Classification** | Local **advisory beta** — [PASS](docs/PRODUCTION_READINESS.md) for `ADVISORY_OPERATOR_READY` |
| **Package** | `hollersports` **0.5.0** |
| **Field-test freeze** | Tag **[`v0.5.0-advisory-beta`](https://github.com/scrimshawlife-ctrl/Hollersports/releases/tag/v0.5.0-advisory-beta)** — prefer this pin for demos |
| **Money / live books** | **Never** — contract-forbidden |
| **Not claimed** | Multi-tenant SaaS GA · PyPI publish · production-scale transformers as betting alpha |

| Capability | State | Notes |
|------------|--------|--------|
| Governance + hashing | **shipped** | Authority locks, fail-closed helpers |
| Packet contracts v1 | **shipped** | JSON Schemas + Pydantic |
| Fixture ingest + source health | **shipped** | `fixtures/day001`–`day003` |
| Free-first live observe | **shipped** | ESPN free; Odds API optional; CI injects |
| Market-first strategies | **shipped** | Consensus · public fade · CLV |
| Model edge (gated) | **shipped** | Calibration ladder + `model_probability` |
| Track F research ML | **shipped** | Features → train → EV annotate → `/v1/ml/*` |
| Track G sequences / axial | **shipped** | Sequences, larger presets, CRPS (optional `[torch]`) |
| Paper guard + ledger | **shipped** | `PAPER_ONLY`, hash-chained JSONL + settlement bank |
| Settlement / promotion / operator day | **shipped** | `run_operator_day` + free-first closed day |
| FastAPI `/v1` | **shipped** | `create_app` factory · port 8000 |
| Operator Workbench | **shipped** | Next.js Cobalt · Today · Book · Health ([design.md](design.md)) |
| CI | **shipped** | Python + operator-web workflows |
| Real money / book placement | **never** | Advisory only |

Full topology: **[docs/atlas/HOLLERSPORTS_ATLAS.md](docs/atlas/HOLLERSPORTS_ATLAS.md)**.  
Documentation map: **[docs/README.md](docs/README.md)**.

## Architecture

```text
fixtures/ ──or── free-first (ESPN ± Odds API)
        │
        ▼
 source_health ──► MarketIngestionPacket
        │
        ▼
 strategy competition (SHADOW_ONLY candidates)
   · consensus / public fade / CLV
   · MODEL_PROBABILITY_EDGE (gated by calibration + opt-in)
        │
        ▼
 execution_guard (PAPER_ONLY) ──► paper ledger
        │
        ▼
 settle ──► performance / reliability / calibration bank
        │
        ▼
 promotion (review only) ──► PROJECTION_ONLY dashboard
        │
        ├── FastAPI /v1  (:8000)
        └── Workbench    (:3000)
```

Optional research path (still advisory): offline **Track F/G** ML → annotate `model_probability` → compete only when the evidence ladder allows.

## Quick start

### 1. Clone and validate (Python)

```bash
git clone https://github.com/scrimshawlife-ctrl/Hollersports.git
cd Hollersports

python3 -m venv .venv && source .venv/bin/activate
make validate          # install + pytest + smoke + calibration suite
make field-test        # freeze receipt → docs/evidence/FIELD_TEST_RECEIPT_v0.5.0.json
```

Pinned field test (recommended for demos):

```bash
git checkout v0.5.0-advisory-beta
python3 -m venv .venv && source .venv/bin/activate
make field-test
```

### 2. Operator UI (local)

```bash
# terminal 1 — API
make api    # http://127.0.0.1:8000

# terminal 2 — Workbench
make web    # http://127.0.0.1:3000  (proxies /v1 → :8000)
```

| Route | Role |
|-------|------|
| **Today** | Action groups: fixture day · free-first live · paper loop |
| **Paper book** | Candidates, paper portfolio, settlement queue — **not** a sportsbook |
| **Health** | Sources, performance, promotion, calibration, reliability, Research ML |

### 3. Library snippet

```python
from pathlib import Path
from hollersports.sources.fixture_adapter import load_fixture_day
from hollersports.pipelines.market_ingestion import run_market_ingestion
from hollersports.pipelines.strategy_competition import run_strategy_competition

day = load_fixture_day(Path("fixtures/day001"))
ingest = run_market_ingestion(day["ingest_payload"])
print(ingest["status"], ingest["authority"])  # INGESTED SHADOW_ONLY

comp = run_strategy_competition(ingest)
print(comp["status"], comp["candidate_count"])
```

Full day: `hollersports.pipelines.operator_day.run_operator_day`.  
Ops detail: [docs/OPERATOR_RUNBOOK.md](docs/OPERATOR_RUNBOOK.md).

### Useful Make targets

| Target | Purpose |
|--------|---------|
| `make validate` | Install, tests, smoke, calibration suite |
| `make field-test` | Smoke + ML e2e + freeze receipt |
| `make api` / `make web` | Local operator stack |
| `make backfill-status` / `make backfill` | Grow paper calibration sample |
| `make free-first` / `make free-first-day` | Optional live observe / closed day |
| `make ml-e2e` / `make ml-compete` | Offline Track F path |
| `make ml-axial-train` | Optional PyTorch axial (`[torch]`) |

## Package layout

| Path | Role |
|------|------|
| `packages/hollersports/` | Primary Python package (`hollersports` 0.5.0) |
| `packages/operator-web/` | Next.js Cobalt Workbench |
| `schemas/json/` | Canonical `*.v1.schema.json` packet contracts |
| `fixtures/day00N/` | Offline multi-league operator days |
| `fixtures/sequences/` | Synthetic multi-poll sequences (Track G) |
| `scripts/` | Smoke, backfill, free-first, field-test, `holler/` ML CLI |
| `tests/{unit,integration,golden,calibration}/` | Layered pytest |
| `docs/` | Contract, runbook, atlas, evidence, agent playbooks |
| `design.md` | Locked Workbench design system (Hallmark) |
| `engine/`, `hollersports-core/` | Legacy reference only — not the operator path |

## Day-one leagues

Architecture is multi-sport. Fixture pack and design day-one set:

**NBA · NFL · MLB · NHL · EPL · MLS** — markets v1: moneyline, spread, total.

## Documentation

| Audience | Start here |
|----------|------------|
| New human operator | [docs/README.md](docs/README.md) → [OPERATOR_RUNBOOK.md](docs/OPERATOR_RUNBOOK.md) |
| Product law | [SYSTEM_CONTRACT.md](docs/SYSTEM_CONTRACT.md) |
| Topology | [atlas/HOLLERSPORTS_ATLAS.md](docs/atlas/HOLLERSPORTS_ATLAS.md) |
| Field-test freeze | [TRACK_F_FREEZE_AND_FIELD_TEST.md](docs/TRACK_F_FREEZE_AND_FIELD_TEST.md) |
| Tests & calibration | [TESTING_AND_CALIBRATION.md](docs/TESTING_AND_CALIBRATION.md) |
| Agents / Hermes | [AGENTS.md](AGENTS.md) · [docs/agents/](docs/agents/README.md) |
| Releases | [RELEASE_NOTES.md](docs/RELEASE_NOTES.md) |
| Readiness evidence | [PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Governance seals

```text
CAPITAL_AUTHORITY=false
EXECUTION_AUTHORITY=false
LIVE_BOOKS=false
ABRAXAS_RUNTIME_REQUIRED=false
MODE=PAPER_ONLY
```

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "packages/hollersports[dev]"
# optional research extras:
# pip install -e "packages/hollersports[ml]"      # sklearn HGB
# pip install -e "packages/hollersports[torch]"   # axial / transformer presets
# pip install -e "packages/hollersports[research]"

pytest tests/ --ignore=hollersports-core -q
cd packages/operator-web && npm install && npm run build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for PR expectations and honesty rules for docs.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## App Store / distribution posture

HollerSports is **not yet** a shipping consumer iOS binary; the Workbench is a local web operator. For **Apple App Store scrutiny** (gambling-adjacent advisory tools), keep this pack green:

| Doc | Role |
|-----|------|
| [docs/APP_STORE_READINESS.md](docs/APP_STORE_READINESS.md) | Guideline map, copy rules, pre-submission checklist, reviewer notes |
| [docs/legal/](docs/legal/README.md) | Privacy · Terms · Age/jurisdiction · Responsible gambling |
| Workbench `ComplianceGate` | First-run age + paper-only acknowledgment |
| CI live-UX grep | Forbids `Place bet` / `LIVE_APPROVED` / guarantee phrases |

**Store copy rule of thumb:** lead with *paper simulation / market intelligence*; never claim real-money books, deposits, or guaranteed ROI. Expect **17+** age rating if listed. Host privacy/terms URLs before any consumer submission.

## Disclaimer

HollerSports is an **advisory and paper-simulation** tool. It does **not** handle real money, place wagers, custody funds, or connect to sportsbooks for execution. It does not guarantee predictive accuracy. Any real-world betting you do is outside this system and your responsibility; sports wagering may be restricted or illegal in your jurisdiction. Operators and users must meet the [age and jurisdiction](docs/legal/AGE_AND_JURISDICTION.md) policy (18+, or 21+ where sports wagering laws require it).
