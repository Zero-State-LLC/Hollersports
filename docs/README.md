# Documentation index

Canonical map for HollerSports docs. Prefer **this index + the freeze tag** over ad-hoc historical notes.

**Product law:** advisory only · paper simulation · **no real money** · **no book placement**.  
See [SYSTEM_CONTRACT.md](SYSTEM_CONTRACT.md).

**App Store / distribution:** [APP_STORE_READINESS.md](APP_STORE_READINESS.md) · [legal/](legal/README.md) (privacy, terms, age, responsible gambling).

---

## Start here (by job)

| Job | Document | First command |
|-----|----------|----------------|
| Run a local operator day | [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) | `make api` · `make web` |
| Field-test the freeze | [TRACK_F_FREEZE_AND_FIELD_TEST.md](TRACK_F_FREEZE_AND_FIELD_TEST.md) | `git checkout v0.5.0-advisory-beta` · `make field-test` |
| Understand topology | [atlas/HOLLERSPORTS_ATLAS.md](atlas/HOLLERSPORTS_ATLAS.md) | — |
| Check readiness claims | [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | Read evidence table first |
| Grow calibration sample | [agents/HERMES_BACKFILL.md](agents/HERMES_BACKFILL.md) | `make backfill-status` |
| Run Track F ML offline | [agents/HERMES_ML.md](agents/HERMES_ML.md) | `make ml-e2e` |
| Agent / automation entry | [../AGENTS.md](../AGENTS.md) · [agents/README.md](agents/README.md) | — |
| UI design system | [../design.md](../design.md) · [../packages/operator-web/README.md](../packages/operator-web/README.md) | `make web` |

---

## Core product docs

| Doc | Contents |
|-----|----------|
| [SYSTEM_CONTRACT.md](SYSTEM_CONTRACT.md) | Ten non-negotiable laws; authority seals |
| [APP_STORE_READINESS.md](APP_STORE_READINESS.md) | Apple / store scrutiny checklist + reviewer narrative |
| [legal/README.md](legal/README.md) | Privacy, terms, age/jurisdiction, responsible gambling |
| [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) | Fixture day, free-first, API + Workbench |
| [TESTING_AND_CALIBRATION.md](TESTING_AND_CALIBRATION.md) | Pytest layers, calibration ladder, Make targets |
| [BACKFILL_AND_NIGHTLY.md](BACKFILL_AND_NIGHTLY.md) | Settlement bank growth notes |
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | Gate model G0–G14 + current posture |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | Version history and tags |
| [ABRAXAS_LINEAGE.md](ABRAXAS_LINEAGE.md) | Concept lineage only — no Abraxas install |
| [MIGRATION_ENGINE.md](MIGRATION_ENGINE.md) | Legacy `engine/` / `hollersports-core` notes |

---

## Freeze, ML, research

| Doc | Contents |
|-----|----------|
| [TRACK_F_FREEZE_AND_FIELD_TEST.md](TRACK_F_FREEZE_AND_FIELD_TEST.md) | **v0.5.0-advisory-beta** field-test freeze checklist |
| [TRACK_F_FUTURE_TRANSFORMERS.md](TRACK_F_FUTURE_TRANSFORMERS.md) | Deferred larger transformers (do not start unless unfrozen) |
| [agents/HERMES_ML.md](agents/HERMES_ML.md) | Features → train → annotate → model edge |
| [arxiv_research_summary.md](arxiv_research_summary.md) | Research task notes (reference) |

---

## Design & specs

| Doc | Contents |
|-----|----------|
| [../design.md](../design.md) | Locked Cobalt Workbench design system (Hallmark) |
| [superpowers/specs/2026-08-04-hollersports-standalone-design.md](superpowers/specs/2026-08-04-hollersports-standalone-design.md) | Product design (standalone operator) |
| [superpowers/specs/2026-08-05-hollersports-ml-pipeline-design.md](superpowers/specs/2026-08-05-hollersports-ml-pipeline-design.md) | ML pipeline design |
| [superpowers/plans/](superpowers/plans/) | Implementation plans (historical track work) |

---

## Evidence (receipts)

Receipts under [evidence/](evidence/) are **machine-writable run outputs**, not marketing claims.

| Receipt / note | Role |
|----------------|------|
| `FIELD_TEST_RECEIPT_v0.5.0.json` | Freeze field-test bundle (`make field-test`) |
| `smoke_operator_day.last.json` | Fixture operator-day smoke |
| `calibration_suite.last.json` | Multi-fixture calibration suite |
| `backfill_calibration.last.json` | Backfill accumulation |
| `ml_pipeline_e2e.last.json` | Offline ML e2e |
| `PRODUCTION_READINESS_*.md` | Dated readiness assessments (read newest continuum first) |

Do not invent metrics in docs. If a number is not in a receipt or test assertion, leave it out or mark `NOT_COMPUTABLE`.

---

## Doc honesty rules

1. **OBSERVED vs PLANNED** — say what ships in tree; do not claim SaaS/money/PyPI without evidence.
2. **Pin freeze for demos** — `v0.5.0-advisory-beta` unless the user asks for `main` tip.
3. **Authority language** — never imply live books, wallets, or capital custody.
4. **Update the atlas** when surfaces change ([atlas/HOLLERSPORTS_ATLAS.md](atlas/HOLLERSPORTS_ATLAS.md)).
5. **Agents start at** [AGENTS.md](../AGENTS.md) and [agents/README.md](agents/README.md).

---

## Related root files

| Path | Role |
|------|------|
| [../README.md](../README.md) | Product entry + quick start |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Dev install, validate, PR checklist |
| [../AGENTS.md](../AGENTS.md) | Agent instructions |
| [../INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md) | Legacy slate-engine integration |
| [../LICENSE](../LICENSE) | Apache 2.0 |
