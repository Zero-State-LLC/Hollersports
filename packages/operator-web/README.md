# HollerSports Operator Web (Cobalt Workbench)

Paper-only operator shell: **Today · Book · Health**.

**Design system:** Hallmark Workbench · atmospheric · Cobalt · N3 rail · Ft4 colophon.  
Canonical tokens: [`tokens.css`](tokens.css) · product design lock: [`../../design.md`](../../design.md).

## Prerequisites

- Node **20+**
- Operator API on `http://127.0.0.1:8000` (`hollersports.api.app:create_app`)

From monorepo root:

```bash
make api   # terminal 1
make web   # terminal 2 — runs npm run dev here
```

## Setup (this package)

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Next rewrites `/v1/*` → `:8000`.

## Build

```bash
npm run build
npm start
```

## Routes

| Route | Role |
|-------|------|
| **Today** | Overview strip + **action board**: fixture day · free-first live · paper loop |
| **Paper book** | Candidates (select + paper), paper portfolio, settlement queue — **not** a sportsbook |
| **Health** | Anchored panels: Research ML, sources, performance, promotion, calibration, reliability, history, run log |

### Typical fixture day (Today)

1. Start API (`make api` from repo root).
2. **Fixture day** group → **Run full day001** (or Ingest only).
3. **Paper loop** → Compete → Paper top-N → Settle.
4. Book → review candidates / portfolio / settlement.
5. Health → calibration + reliability (and optional Research ML train/annotate).

Model edge: enable **Allow model edge** on Today only when calibration evidence is `RELIABLE` (see Health → Calibration). Still `SHADOW_ONLY` — no money.

## Guardrails

- Mode is locked **PAPER_ONLY** (colophon). No live capital path.
- No live-wagering UX labels or live-approved mode strings in source (CI greps the operator-web tree).
- First-run **ComplianceGate** requires age + jurisdiction + paper-only acknowledgment (App Store / distribution posture).
- See [docs/APP_STORE_READINESS.md](../../docs/APP_STORE_READINESS.md) and [docs/legal/](../../docs/legal/README.md).
- Prefer utility classes from `globals.css` — no ad-hoc spacing inventing outside tokens.

## Related

- [docs/OPERATOR_RUNBOOK.md](../../docs/OPERATOR_RUNBOOK.md)
- [docs/SYSTEM_CONTRACT.md](../../docs/SYSTEM_CONTRACT.md)
- [design.md](../../design.md)
