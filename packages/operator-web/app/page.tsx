"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthorityChip, toneForStatus } from "@/components/AuthorityChip";
import {
  ApiError,
  cacheCompetition,
  fieldOrDash,
  getDashboard,
  postCompete,
  postFreeFirst,
  postFreeFirstDay,
  postFullDay,
  postIngest,
  postPaper,
  postSettle,
  type Json,
} from "@/lib/api";

type ActionId =
  | "ingest"
  | "compete"
  | "paper"
  | "settle"
  | "refresh"
  | "fullday"
  | "freefirst"
  | "freefirstday";

function panelField(
  dashboard: Json | null,
  path: string[],
): { text: string; reason?: string } {
  if (!dashboard) {
    return { text: "—", reason: "dashboard not loaded" };
  }
  let cur: unknown = dashboard;
  for (const key of path) {
    if (cur === null || cur === undefined || typeof cur !== "object") {
      return { text: "—", reason: `missing ${path.join(".")}` };
    }
    cur = (cur as Record<string, unknown>)[key];
  }
  return fieldOrDash(cur, `missing ${path.join(".")}`);
}

const FIXTURES = ["day001", "day002", "day003"] as const;
type FixtureId = (typeof FIXTURES)[number];

const FREE_FIRST_LEAGUES = ["ALL", "NBA", "NFL", "MLB", "NHL", "MLS", "EPL"] as const;
type FreeFirstLeagueChoice = (typeof FREE_FIRST_LEAGUES)[number];

export default function TodayPage() {
  const [dashboard, setDashboard] = useState<Json | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<ActionId | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [fixture, setFixture] = useState<FixtureId>("day001");
  const [allowModelEdge, setAllowModelEdge] = useState(false);
  const [freeFirstLeague, setFreeFirstLeague] =
    useState<FreeFirstLeagueChoice>("ALL");

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const d = await getDashboard();
      setDashboard(d);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "dashboard fetch failed";
      setError(msg);
      setDashboard(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function runAction(id: ActionId, fn: () => Promise<Json>) {
    setBusy(id);
    setError(null);
    setLastAction(null);
    try {
      const result = await fn();
      if (id === "compete") {
        cacheCompetition(result);
      }
      if (id === "freefirst") {
        const ingestCount = result.ingest_count;
        const competed = result.competed_event_count;
        const cands = result.candidate_count;
        setLastAction(
          `${id} → ${String(result.status ?? "ok")}` +
            (ingestCount != null ? ` · ingest ${String(ingestCount)}` : "") +
            (competed != null ? ` · competed ${String(competed)}` : "") +
            (cands != null ? ` · candidates ${String(cands)}` : ""),
        );
      } else if (id === "settle") {
        const entries = Array.isArray(result.entries) ? result.entries : [];
        const pending = entries.filter(
          (e) =>
            e &&
            typeof e === "object" &&
            String((e as { status?: unknown }).status ?? "").toUpperCase() ===
              "PENDING",
        ).length;
        const settled = entries.length - pending;
        setLastAction(
          `${id} → ${String(result.status ?? "ok")} · settled ${settled} · pending ${pending}` +
            (result.result_count != null
              ? ` · results ${String(result.result_count)}`
              : ""),
        );
      } else {
        setLastAction(`${id} → ${String(result.status ?? "ok")}`);
      }
      await refresh();
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : `${id} failed`;
      setError(msg);
    } finally {
      setBusy(null);
    }
  }

  const runId = panelField(dashboard, ["run_id"]);
  const status = panelField(dashboard, ["status"]);
  const authority = panelField(dashboard, ["authority"]);
  const capital = panelField(dashboard, ["capital_authority"]);
  const portfolioId = panelField(dashboard, ["portfolio_id"]);
  const approved = panelField(dashboard, [
    "panels",
    "paper_portfolio_summary",
    "approved_count",
  ]);
  const rejected = panelField(dashboard, [
    "panels",
    "paper_portfolio_summary",
    "rejected_count",
  ]);
  const settlementPending = panelField(dashboard, [
    "panels",
    "settlement_queue",
    "pending",
  ]);
  const promoStatus = panelField(dashboard, [
    "panels",
    "promotion_gate_status",
    "status",
  ]);
  const sourceStatus = panelField(dashboard, ["panels", "sources", "status"]);
  const slateIngest = panelField(dashboard, ["panels", "slate", "ingest_count"]);
  const slateCompeted = panelField(dashboard, [
    "panels",
    "slate",
    "competed_event_count",
  ]);
  const slateCandidates = panelField(dashboard, [
    "panels",
    "slate",
    "candidate_count",
  ]);
  const slatePath = panelField(dashboard, ["panels", "slate", "path"]);

  const disabled = busy !== null || loading;

  return (
    <>
      <header className="page-header">
        <h1>Today</h1>
        <div className="actions-row">
          <AuthorityChip
            label={String(dashboard?.authority ?? "PROJECTION_ONLY")}
            tone={toneForStatus(dashboard?.authority)}
          />
          <button
            type="button"
            className="btn"
            disabled={disabled}
            aria-busy={busy === "refresh" || loading || undefined}
            onClick={() =>
              void runAction("refresh", async () => {
                await refresh();
                return { status: "REFRESHED" };
              })
            }
          >
            {busy === "refresh" || loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      <p className="lede" role="note">
        Operator day board — observe markets, score advisory candidates, run{" "}
        <strong>paper simulation</strong>. No real money. No sportsbook
        placement. Performance figures are sim metrics only.
      </p>

      <section className="section" aria-label="Overview">
        <h2 className="section-title">Overview</h2>
        <dl className="overview-strip">
          <OverviewField label="run_id" value={runId} />
          <OverviewField label="status" value={status} />
          <OverviewField label="authority" value={authority} />
          <OverviewField label="capital_authority" value={capital} />
          <OverviewField label="portfolio_id" value={portfolioId} />
          <OverviewField label="paper approved" value={approved} />
          <OverviewField label="paper rejected" value={rejected} />
          <OverviewField label="settlement pending" value={settlementPending} />
          <OverviewField label="promotion" value={promoStatus} />
          <OverviewField label="ingest status" value={sourceStatus} />
          <OverviewField label="slate path" value={slatePath} />
          <OverviewField label="slate ingest_count" value={slateIngest} />
          <OverviewField label="slate competed" value={slateCompeted} />
          <OverviewField label="slate candidates" value={slateCandidates} />
        </dl>
      </section>

      <section className="section" aria-label="Actions">
        <h2 className="section-title">Actions</h2>

        <div className="controls-bar">
          <label className="field-label">
            Fixture
            <select
              className="mono"
              value={fixture}
              disabled={disabled}
              aria-label="Fixture day"
              onChange={(e) => setFixture(e.target.value as FixtureId)}
            >
              {FIXTURES.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
          <label
            className="field-label"
            title="Requests forecast weighting; model edge unlocks only when evidence calibration is RELIABLE (see Health → Calibration). Markets need model_probability (day002). Still SHADOW_ONLY — no money."
          >
            <input
              type="checkbox"
              checked={allowModelEdge}
              disabled={disabled}
              onChange={(e) => setAllowModelEdge(e.target.checked)}
            />
            Allow model edge (evidence calibration)
          </label>
          <label
            className="field-label"
            title="Day-one leagues for free-first live observe. Default: all. Advisory only — no money."
          >
            Free-first leagues
            <select
              className="mono"
              value={freeFirstLeague}
              disabled={disabled}
              aria-label="Free-first leagues"
              onChange={(e) =>
                setFreeFirstLeague(e.target.value as FreeFirstLeagueChoice)
              }
            >
              {FREE_FIRST_LEAGUES.map((id) => (
                <option key={id} value={id}>
                  {id === "ALL" ? "All day-one" : id}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="action-board">
          <div className="action-group">
            <h3 className="action-group-title">Fixture day</h3>
            <p className="action-group-hint">
              Offline paper loop on fixture days. Primary: full day pipeline.
            </p>
            <div className="actions-row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={disabled}
                aria-busy={busy === "fullday" || undefined}
                onClick={() =>
                  void runAction("fullday", () => postFullDay(fixture))
                }
              >
                {busy === "fullday" ? "Running day…" : `Run full ${fixture}`}
              </button>
              <button
                type="button"
                className="btn"
                disabled={disabled}
                aria-busy={busy === "ingest" || undefined}
                onClick={() =>
                  void runAction("ingest", () => postIngest(fixture))
                }
              >
                {busy === "ingest" ? "Ingesting…" : `Ingest ${fixture}`}
              </button>
            </div>
          </div>

          <div className="action-group">
            <h3 className="action-group-title">Free-first live</h3>
            <p className="action-group-hint">
              Network observation (ESPN; Odds API if keyed). Non-finals stay
              PENDING. No money.
            </p>
            <div className="actions-row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={disabled}
                aria-busy={busy === "freefirstday" || undefined}
                title="Observe → compete → paper → ESPN finals settle → calibration bank. Network; non-final stay PENDING. No money."
                onClick={() =>
                  void runAction("freefirstday", () =>
                    postFreeFirstDay({
                      fetch_espn_finals: true,
                      leagues:
                        freeFirstLeague === "ALL"
                          ? undefined
                          : [freeFirstLeague],
                    }),
                  )
                }
              >
                {busy === "freefirstday"
                  ? "Running free-first day…"
                  : "Free-first closed day"}
              </button>
              <button
                type="button"
                className="btn"
                disabled={disabled}
                aria-busy={busy === "freefirst" || undefined}
                title="Optional network observation (ESPN; Odds API if key set). No money."
                onClick={() =>
                  void runAction("freefirst", () =>
                    postFreeFirst({
                      espn_only: false,
                      auto_compete: true,
                      leagues:
                        freeFirstLeague === "ALL"
                          ? undefined
                          : [freeFirstLeague],
                    }),
                  )
                }
              >
                {busy === "freefirst" ? "Observing…" : "Live observe"}
              </button>
            </div>
          </div>

          <div className="action-group">
            <h3 className="action-group-title">Paper loop</h3>
            <p className="action-group-hint">
              Compete · paper · settle on the current slate. Advisory simulation
              only.
            </p>
            <div className="actions-row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={disabled}
                aria-busy={busy === "compete" || undefined}
                onClick={() =>
                  void runAction("compete", () =>
                    postCompete({ allow_forecast_weighting: allowModelEdge }),
                  )
                }
              >
                {busy === "compete" ? "Competing…" : "Compete"}
              </button>
              <button
                type="button"
                className="btn"
                disabled={disabled}
                aria-busy={busy === "paper" || undefined}
                onClick={() => void runAction("paper", () => postPaper())}
              >
                {busy === "paper" ? "Papering…" : "Paper top-N"}
              </button>
              <button
                type="button"
                className="btn"
                disabled={disabled}
                aria-busy={busy === "settle" || undefined}
                title={
                  slatePath.text === "free-first"
                    ? "Settle via live ESPN scoreboard finals when available; non-final stay PENDING. No money."
                    : "Settle against fixture results.json when a fixture day is loaded. No money."
                }
                onClick={() =>
                  void runAction("settle", () => {
                    const isFreeFirst = slatePath.text === "free-first";
                    const league =
                      freeFirstLeague === "ALL" ? undefined : [freeFirstLeague];
                    return postSettle(
                      isFreeFirst
                        ? { fetch_espn: true, leagues: league }
                        : {},
                    );
                  })
                }
              >
                {busy === "settle"
                  ? "Settling…"
                  : slatePath.text === "free-first"
                    ? "Settle (ESPN finals)"
                    : "Settle"}
              </button>
            </div>
          </div>
        </div>

        {error && (
          <p className="error-line" role="alert">
            {error}
          </p>
        )}
        {lastAction && !error && (
          <p className="status-line" aria-live="polite">
            {lastAction}
          </p>
        )}
      </section>
    </>
  );
}

function OverviewField({
  label,
  value,
}: {
  label: string;
  value: { text: string; reason?: string };
}) {
  return (
    <div className="overview-field">
      <dt>{label}</dt>
      <dd title={value.reason}>
        {value.text}
        {value.reason && value.text === "—" && (
          <span className="muted"> · {value.reason}</span>
        )}
      </dd>
    </div>
  );
}
