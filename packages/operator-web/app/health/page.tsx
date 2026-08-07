"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthorityChip, toneForStatus } from "@/components/AuthorityChip";
import { DataTable, type Column } from "@/components/DataTable";
import {
  ApiError,
  fieldOrDash,
  getDashboard,
  getHealth,
  getPortfolio,
  getPromotion,
  getCalibration,
  getReliability,
  getReliabilityHistory,
  getMlStatus,
  postMlAnnotate,
  postMlRetrainCheck,
  postMlTrain,
  type Json,
} from "@/lib/api";

type SourceRow = {
  key: string;
  id: string;
  type: string;
  enabled: string;
};

type ReliabilityRow = {
  key: string;
  dimension: string;
  bucket: string;
  n: string;
  hit: string;
  roi: string;
};

type HistoryRow = {
  key: string;
  recorded: string;
  status: string;
  sample: string;
  buckets: string;
  hash: string;
};

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

function asList(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

const HEALTH_ANCHORS = [
  { id: "ml", label: "ML" },
  { id: "sources", label: "Sources" },
  { id: "performance", label: "Performance" },
  { id: "promotion", label: "Promotion" },
  { id: "calibration", label: "Calibration" },
  { id: "reliability", label: "Reliability" },
  { id: "history", label: "History" },
  { id: "run-log", label: "Run log" },
] as const;

export default function HealthPage() {
  const [health, setHealth] = useState<Json | null>(null);
  const [dashboard, setDashboard] = useState<Json | null>(null);
  const [portfolio, setPortfolio] = useState<Json | null>(null);
  const [promotion, setPromotion] = useState<Json | null>(null);
  const [reliability, setReliability] = useState<Json | null>(null);
  const [reliabilityHistory, setReliabilityHistory] = useState<Json | null>(
    null,
  );
  const [calibration, setCalibration] = useState<Json | null>(null);
  const [mlStatus, setMlStatus] = useState<Json | null>(null);
  const [mlBusy, setMlBusy] = useState(false);
  const [mlNote, setMlNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const [h, d, p, promo, rel, hist, cal, ml] = await Promise.all([
        getHealth(),
        getDashboard(),
        getPortfolio(),
        getPromotion(),
        getReliability(),
        getReliabilityHistory(20),
        getCalibration(true),
        getMlStatus(),
      ]);
      setHealth(h);
      setDashboard(d);
      setPortfolio(p);
      setPromotion(promo);
      setReliability(rel);
      setReliabilityHistory(hist);
      setCalibration(cal);
      setMlStatus(ml);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "health load failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const panels = asRecord(dashboard?.panels);
  const sourcesPanel = asRecord(panels.sources);
  const sourceHealth = asRecord(sourcesPanel.source_health);
  const performance = asRecord(
    portfolio?.performance ?? panels.performance_metrics,
  );
  const promo = asRecord(promotion);
  const registrySources = asList(health?.sources).filter(
    (s): s is Record<string, unknown> => !!s && typeof s === "object",
  );

  const sourceRows: SourceRow[] = registrySources.map((s, i) => ({
    key: String(s.id ?? i),
    id: String(s.id ?? "—"),
    type: String(s.type ?? "—"),
    enabled: String(s.enabled ?? "—"),
  }));

  const sourceColumns: Column<SourceRow>[] = [
    {
      key: "id",
      header: "Source",
      render: (r) => <span className="mono">{r.id}</span>,
    },
    {
      key: "type",
      header: "Type",
      render: (r) => <span className="mono">{r.type}</span>,
    },
    {
      key: "enabled",
      header: "Enabled",
      render: (r) => r.enabled,
    },
  ];

  const perfKeys = [
    "status",
    "sample_size",
    "roi",
    "hit_rate",
    "clv_retention",
    "max_drawdown",
    "volatility",
    "sharpe_like_ratio",
    "profit_factor",
    "average_stake",
    "reason",
  ] as const;

  const passedGates = asList(promo.passed_gates).map(String);
  const failedGates = asList(promo.failed_gates).map(String);

  const reliabilityRows: ReliabilityRow[] = asList(reliability?.buckets)
    .filter((b): b is Record<string, unknown> => !!b && typeof b === "object")
    .map((b, i) => ({
      key: `${String(b.dimension)}|${String(b.key)}|${i}`,
      dimension: String(b.dimension ?? "—"),
      bucket: String(b.key ?? "—"),
      n: String(b.sample_size ?? "—"),
      hit: String(b.hit_rate ?? "—"),
      roi: String(b.sim_roi ?? "—"),
    }));

  const historyRows: HistoryRow[] = asList(reliabilityHistory?.entries)
    .filter((e): e is Record<string, unknown> => !!e && typeof e === "object")
    .map((e, i) => {
      const hash = String(e.entry_hash ?? "");
      return {
        key: hash || `hist-${i}`,
        recorded: String(e.recorded_at ?? "—"),
        status: String(e.status ?? "—"),
        sample: String(e.sample_size ?? "—"),
        buckets: String(e.bucket_count ?? "—"),
        hash: hash ? `${hash.slice(0, 10)}…` : "—",
      };
    });

  const runLog: { key: string; label: string; value: string }[] = [
    {
      key: "run_id",
      label: "run_id",
      value: fieldOrDash(dashboard?.run_id).text,
    },
    {
      key: "dashboard_status",
      label: "dashboard.status",
      value: fieldOrDash(dashboard?.status).text,
    },
    {
      key: "dashboard_authority",
      label: "dashboard.authority",
      value: fieldOrDash(dashboard?.authority).text,
    },
    {
      key: "portfolio_status",
      label: "portfolio.status",
      value: fieldOrDash(portfolio?.status, "empty portfolio").text,
    },
    {
      key: "portfolio_run",
      label: "portfolio.run_id",
      value: fieldOrDash(portfolio?.run_id).text,
    },
    {
      key: "health_status",
      label: "api.health",
      value: fieldOrDash(health?.status).text,
    },
    {
      key: "mode",
      label: "mode",
      value: fieldOrDash(health?.mode, "not reported").text,
    },
    {
      key: "capital",
      label: "capital_authority",
      value: fieldOrDash(health?.capital_authority).text,
    },
  ];

  const mlModelId =
    mlStatus?.last_train &&
    typeof mlStatus.last_train === "object" &&
    mlStatus.last_train !== null &&
    "model_id" in (mlStatus.last_train as object)
      ? String((mlStatus.last_train as { model_id?: string }).model_id ?? "")
      : "";

  return (
    <>
      <header className="page-header">
        <h1>Health</h1>
        <div className="actions-row">
          <AuthorityChip
            label={String(health?.status ?? (loading ? "…" : "—"))}
            tone={toneForStatus(health?.status)}
          />
          <button
            type="button"
            className="btn"
            disabled={loading}
            aria-busy={loading || undefined}
            onClick={() => void load()}
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </header>

      <p className="lede" role="note">
        Advisory only — metrics are paper simulation for advice quality. No real
        money. No book placement.
      </p>

      <nav className="health-anchors" aria-label="Health sections">
        {HEALTH_ANCHORS.map((a) => (
          <a key={a.id} href={`#${a.id}`}>
            {a.label}
          </a>
        ))}
      </nav>

      {loading && !error && (
        <p className="muted" aria-live="polite">
          Loading health surfaces…
        </p>
      )}

      {error && (
        <p className="error-line" role="alert">
          {error} · Check API on :8000 (`make api`) then Refresh.
        </p>
      )}

      <section className="panel" id="ml" aria-label="Track F ML">
        <div className="panel-head">
          <h2 className="section-title">Research ML (Track F)</h2>
          <AuthorityChip
            label={String(mlStatus?.status ?? "—")}
            tone={toneForStatus(mlStatus?.status)}
          />
        </div>
        <p className="panel-lede">
          Offline features → train → annotate last ingest with{" "}
          <span className="mono">model_probability</span>. Advisory only — no
          money. Fail closed without ensemble.
        </p>
        <div className="actions-row mb-sm">
          <span className="meta-line">
            ensemble={String(mlStatus?.ensemble_present ? "yes" : "no")}
            {mlModelId ? ` · ${mlModelId}` : ""}
          </span>
        </div>
        <div className="actions-row">
          <button
            type="button"
            className="btn btn-primary"
            disabled={loading || mlBusy}
            aria-busy={mlBusy || undefined}
            onClick={() => {
              void (async () => {
                setMlBusy(true);
                setMlNote(null);
                try {
                  const r = await postMlTrain({
                    train_fixtures: ["day001", "day002"],
                  });
                  setMlNote(
                    `trained ${String(r.model_id ?? "")} · T=${String(
                      (r.metrics as { temperature?: number } | undefined)
                        ?.temperature ?? "—",
                    )}`,
                  );
                  setMlStatus(await getMlStatus());
                } catch (e) {
                  setMlNote(
                    e instanceof ApiError
                      ? e.message
                      : e instanceof Error
                        ? e.message
                        : "train failed",
                  );
                } finally {
                  setMlBusy(false);
                }
              })();
            }}
          >
            {mlBusy ? "Working…" : "Train day001+002"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={loading || mlBusy}
            aria-busy={mlBusy || undefined}
            title="Requires a prior ingest on Today. Annotates markets, then competes with auto-calibration (model edge only if ladder allows)."
            onClick={() => {
              void (async () => {
                setMlBusy(true);
                setMlNote(null);
                try {
                  // Evidence gate: auto calibration from settlement bank — never
                  // force RELIABLE from the Workbench (keeps calibration ladder intact).
                  const r = await postMlAnnotate({
                    auto_compete: true,
                    allow_forecast_weighting: true,
                    use_auto_calibration: true,
                  });
                  setMlNote(
                    `annotated ${String(r.annotated_markets ?? 0)} markets · model-edge ${String(
                      r.model_edge_enabled ?? false,
                    )} · model-edge cands ${String(
                      r.model_edge_candidate_count ?? 0,
                    )}`,
                  );
                  setMlStatus(await getMlStatus());
                  await load();
                } catch (e) {
                  setMlNote(
                    e instanceof ApiError
                      ? e.message
                      : e instanceof Error
                        ? e.message
                        : "annotate failed",
                  );
                } finally {
                  setMlBusy(false);
                }
              })();
            }}
          >
            Annotate + compete
          </button>
          <button
            type="button"
            className="btn"
            disabled={loading || mlBusy}
            aria-busy={mlBusy || undefined}
            title="Advisory only: evaluate ensemble Brier vs baseline; never auto-trains."
            onClick={() => {
              void (async () => {
                setMlBusy(true);
                setMlNote(null);
                try {
                  const r = await postMlRetrainCheck();
                  setMlNote(
                    `retrain ${String(r.status ?? "—")} · ${String(r.reason ?? "")}`,
                  );
                  setMlStatus(await getMlStatus());
                } catch (e) {
                  setMlNote(
                    e instanceof ApiError
                      ? e.message
                      : e instanceof Error
                        ? e.message
                        : "retrain-check failed",
                  );
                } finally {
                  setMlBusy(false);
                }
              })();
            }}
          >
            Retrain check
          </button>
        </div>
        {mlNote && (
          <p className="status-line mono" aria-live="polite">
            {mlNote}
          </p>
        )}
      </section>

      <section className="panel" id="sources" aria-label="Sources">
        <div className="panel-head">
          <h2 className="section-title">Sources</h2>
          <div className="actions-row">
            <AuthorityChip
              label={String(
                sourceHealth.status ?? sourcesPanel.status ?? "—",
              )}
              tone={toneForStatus(
                sourceHealth.status ?? sourcesPanel.status,
              )}
              title={
                sourceHealth.reason != null
                  ? String(sourceHealth.reason)
                  : undefined
              }
            />
            <span className="meta-line">
              source_id={String(sourcesPanel.source_id ?? "—")}
            </span>
          </div>
        </div>
        <DataTable
          columns={sourceColumns}
          rows={sourceRows}
          rowKey={(r) => r.key}
          emptyMessage={
            loading
              ? "Loading registry…"
              : "No sources yet — start API and Refresh, or run a fixture day on Today"
          }
        />
        {asList(sourceHealth.missing_required_fields).length > 0 && (
          <p className="status-line">
            missing_required_fields:{" "}
            {asList(sourceHealth.missing_required_fields)
              .map(String)
              .join(", ")}
          </p>
        )}
      </section>

      <section className="panel" id="performance" aria-label="Performance">
        <div className="panel-head">
          <h2 className="section-title">Performance</h2>
          <AuthorityChip
            label={String(performance.status ?? "—")}
            tone={toneForStatus(performance.status)}
            title={
              performance.reason != null
                ? String(performance.reason)
                : undefined
            }
          />
        </div>
        <dl className="kv-list">
          {perfKeys.map((k) => {
            const f = fieldOrDash(performance[k], `missing ${k}`);
            return (
              <div key={k} className="display-contents">
                <dt>{k}</dt>
                <dd className="tabular" title={f.reason}>
                  {f.text}
                  {f.reason && f.text === "—" ? (
                    <span className="muted"> · {f.reason}</span>
                  ) : null}
                </dd>
              </div>
            );
          })}
        </dl>
      </section>

      <section className="panel" id="promotion" aria-label="Promotion">
        <div className="panel-head">
          <h2 className="section-title">Promotion</h2>
          <div className="actions-row">
            <AuthorityChip
              label={String(promo.status ?? "—")}
              tone={toneForStatus(promo.status)}
              title={promo.reason != null ? String(promo.reason) : undefined}
            />
            <span className="meta-line">
              target={String(promo.target_id ?? "—")} /{" "}
              {String(promo.target_type ?? "—")}
            </span>
          </div>
        </div>
        <div className="gate-grid">
          <div>
            <h3 className="section-title">Passed gates</h3>
            <ul className="gate-list">
              {passedGates.length === 0 ? (
                <li className="muted">— none</li>
              ) : (
                passedGates.map((g) => (
                  <li key={g}>
                    <AuthorityChip label={g} tone="neutral" />
                  </li>
                ))
              )}
            </ul>
          </div>
          <div>
            <h3 className="section-title">Failed gates</h3>
            <ul className="gate-list">
              {failedGates.length === 0 ? (
                <li className="muted">— none</li>
              ) : (
                failedGates.map((g) => (
                  <li key={g}>
                    <AuthorityChip label={g} tone="fail" />
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>
      </section>

      <section className="panel" id="calibration" aria-label="Calibration">
        <div className="panel-head">
          <h2 className="section-title">Calibration</h2>
          <AuthorityChip
            label={String(calibration?.status ?? (loading ? "…" : "EMPTY"))}
            tone={toneForStatus(calibration?.status)}
          />
        </div>
        <p className="panel-lede">
          Evidence ladder from settled paper outcomes. Model edge unlocks only
          when status is RELIABLE and forecast weighting is allowed — still
          SHADOW_ONLY, no money.
        </p>
        <p className="meta-line mb-sm">
          sample={String(calibration?.sample_size ?? "—")} · hit=
          {String(calibration?.hit_rate ?? "—")} · sim_roi=
          {String(calibration?.sim_roi ?? "—")} · model_edge=
          {String(calibration?.model_edge_allowed ?? "—")}
        </p>
        <dl className="kv-list">
          {(
            [
              "reliability_status",
              "allow_forecast_weighting",
              "model_edge_allowed",
              "sample_size",
              "hit_rate",
              "sim_roi",
            ] as const
          ).map((k) => {
            const f = fieldOrDash(calibration?.[k], `missing ${k}`);
            return (
              <div key={k} className="display-contents">
                <dt>{k}</dt>
                <dd className="tabular">{f.text}</dd>
              </div>
            );
          })}
        </dl>
        {asList(calibration?.failed_gates).length > 0 && (
          <p className="status-line">
            failed_gates:{" "}
            {asList(calibration?.failed_gates).map(String).join(", ")}
          </p>
        )}
      </section>

      <section className="panel" id="reliability" aria-label="Advice reliability">
        <div className="panel-head">
          <h2 className="section-title">Advice reliability</h2>
          <div className="actions-row">
            <AuthorityChip
              label={String(reliability?.status ?? (loading ? "…" : "EMPTY"))}
              tone={toneForStatus(reliability?.status)}
            />
            <span className="meta-line">
              sample={String(reliability?.sample_size ?? "—")} · buckets=
              {String(reliability?.bucket_count ?? "—")}
            </span>
          </div>
        </div>
        <p className="panel-lede">
          Simulation hit rate / ROI by strategy, league, and market — not real
          money.
        </p>
        <DataTable
          columns={[
            {
              key: "dimension",
              header: "Dimension",
              render: (r: ReliabilityRow) => (
                <span className="mono">{r.dimension}</span>
              ),
            },
            {
              key: "bucket",
              header: "Bucket",
              render: (r: ReliabilityRow) => (
                <span className="mono">{r.bucket}</span>
              ),
            },
            {
              key: "n",
              header: "n",
              align: "right" as const,
              tabular: true,
              render: (r: ReliabilityRow) => r.n,
            },
            {
              key: "hit",
              header: "hit_rate",
              align: "right" as const,
              tabular: true,
              render: (r: ReliabilityRow) => r.hit,
            },
            {
              key: "roi",
              header: "sim_roi (paper)",
              align: "right" as const,
              tabular: true,
              render: (r: ReliabilityRow) => r.roi,
            },
          ]}
          rows={reliabilityRows}
          rowKey={(r) => r.key}
          emptyMessage={
            loading
              ? "Loading reliability…"
              : "No settled advice yet — run full fixture day on Today, then Refresh"
          }
        />
      </section>

      <section className="panel" id="history" aria-label="Reliability history">
        <div className="panel-head">
          <h2 className="section-title">Reliability history</h2>
          <div className="actions-row">
            <AuthorityChip
              label={String(
                reliabilityHistory?.status ?? (loading ? "…" : "EMPTY"),
              )}
              tone={toneForStatus(reliabilityHistory?.status)}
            />
            <span className="meta-line">
              snapshots={String(reliabilityHistory?.count ?? "—")}
            </span>
          </div>
        </div>
        <p className="panel-lede">
          Append-only snapshots after each settle — advice calibration trail,
          not a bank ledger.
        </p>
        <DataTable
          columns={[
            {
              key: "recorded",
              header: "recorded_at",
              render: (r: HistoryRow) => (
                <span className="mono">{r.recorded}</span>
              ),
            },
            {
              key: "status",
              header: "status",
              render: (r: HistoryRow) => r.status,
            },
            {
              key: "sample",
              header: "sample",
              align: "right" as const,
              tabular: true,
              render: (r: HistoryRow) => r.sample,
            },
            {
              key: "buckets",
              header: "buckets",
              align: "right" as const,
              tabular: true,
              render: (r: HistoryRow) => r.buckets,
            },
            {
              key: "hash",
              header: "entry_hash",
              render: (r: HistoryRow) => (
                <span className="mono" title={r.key}>
                  {r.hash}
                </span>
              ),
            },
          ]}
          rows={historyRows}
          rowKey={(r) => r.key}
          emptyMessage={
            loading
              ? "Loading history…"
              : "No history yet — settle a paper day (Today → full fixture day), then Refresh"
          }
        />
      </section>

      <section className="panel" id="run-log" aria-label="Run log">
        <div className="panel-head">
          <h2 className="section-title">Run log</h2>
        </div>
        <dl className="kv-list">
          {runLog.map((row) => (
            <div key={row.key} className="display-contents">
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}
