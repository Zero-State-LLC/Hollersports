"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AuthorityChip, toneForStatus } from "@/components/AuthorityChip";
import { DataTable, type Column } from "@/components/DataTable";
import {
  ApiError,
  cacheCompetition,
  candidateKey,
  getCandidates,
  getDashboard,
  getPortfolio,
  postCompete,
  postPaper,
  postSettle,
  readCachedCompetition,
  type Json,
} from "@/lib/api";

type Candidate = {
  key: string;
  strategy_id: string;
  strategy_family: string;
  event_id: string;
  market_id: string;
  selection: string;
  score: number | null;
  confidence: number | null;
  status: string;
  authority: string;
  reason?: string;
};

type PortfolioRow = {
  key: string;
  entry_id: string;
  event_id: string;
  market_id: string;
  selection: string;
  paper_stake: number | null;
  paper_result: string;
  expected_value: number | null;
  settled_value: number | null;
  status: string;
};

type SettlementRow = {
  key: string;
  entry_id: string;
  event_id: string;
  market_id: string;
  selection: string;
  status: string;
  pnl: number | null;
  result_source: string;
  final_score: string;
  reason?: string;
};

function asList(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function numOrNull(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))) {
    return Number(v);
  }
  return null;
}

function parseCandidates(competition: Json | null): Candidate[] {
  if (!competition) return [];
  const raw = asList(competition.candidates);
  return raw
    .filter((c): c is Record<string, unknown> => !!c && typeof c === "object")
    .map((c) => {
      const strategy_id = String(c.strategy_id ?? "");
      const event_id = String(c.event_id ?? "");
      const market_id = String(c.market_id ?? "");
      const selection = String(c.selection ?? "");
      return {
        key: candidateKey({ strategy_id, market_id, selection }),
        strategy_id,
        strategy_family: String(c.strategy_family ?? ""),
        event_id,
        market_id,
        selection,
        score: numOrNull(c.score),
        confidence: numOrNull(c.confidence),
        status: String(c.status ?? "—"),
        authority: String(c.authority ?? "—"),
        reason: c.reason != null ? String(c.reason) : undefined,
      };
    });
}

function parsePortfolio(packet: Json | null): PortfolioRow[] {
  if (!packet) return [];
  const entries = [
    ...asList(packet.ledger_entries),
    ...asList(packet.portfolio_entries),
  ];
  // De-dupe by entry_id when both lists present.
  const seen = new Set<string>();
  const rows: PortfolioRow[] = [];
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    if (!e || typeof e !== "object") continue;
    const rec = e as Record<string, unknown>;
    const entry_id = String(rec.entry_id ?? rec.id ?? `row-${i}`);
    if (seen.has(entry_id)) continue;
    seen.add(entry_id);
    rows.push({
      key: entry_id,
      entry_id,
      event_id: String(rec.event_id ?? "—"),
      market_id: String(rec.market_id ?? "—"),
      selection: String(rec.selection ?? "—"),
      paper_stake: numOrNull(rec.paper_stake ?? rec.stake),
      paper_result: String(rec.paper_result ?? rec.status ?? "PENDING"),
      expected_value: numOrNull(rec.expected_value),
      settled_value: numOrNull(rec.settled_value),
      status: String(rec.status ?? rec.paper_result ?? "—"),
    });
  }
  return rows;
}

function parseSettlements(packet: Json | null): SettlementRow[] {
  if (!packet) return [];
  const batch =
    packet.settlements && typeof packet.settlements === "object"
      ? (packet.settlements as Record<string, unknown>)
      : packet;
  const entries = asList(
    (batch as { entries?: unknown }).entries ?? packet.settlement_entries,
  );
  return entries
    .filter((e): e is Record<string, unknown> => !!e && typeof e === "object")
    .map((e, i) => ({
      key: String(e.entry_id ?? e.id ?? `settle-${i}`),
      entry_id: String(e.entry_id ?? e.id ?? `settle-${i}`),
      event_id: String(e.event_id ?? "—"),
      market_id: String(e.market_id ?? "—"),
      selection: String(e.selection ?? "—"),
      status: String(e.status ?? "PENDING"),
      pnl: numOrNull(e.pnl),
      result_source: String(e.result_source ?? e.source ?? "—"),
      final_score:
        e.final_score != null && String(e.final_score) !== ""
          ? String(e.final_score)
          : "—",
      reason: e.reason != null ? String(e.reason) : undefined,
    }));
}

function fmtNum(n: number | null, digits = 4): string {
  if (n === null) return "—";
  return n.toFixed(digits);
}

export default function BookPage() {
  const [competition, setCompetition] = useState<Json | null>(null);
  const [portfolio, setPortfolio] = useState<Json | null>(null);
  const [slatePath, setSlatePath] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusLine, setStatusLine] = useState<string | null>(null);

  const load = useCallback(async (refreshCompete: boolean) => {
    setError(null);
    try {
      const [port, dash] = await Promise.all([
        getPortfolio(),
        getDashboard().catch(() => null),
      ]);
      setPortfolio(port);
      const path = (dash?.panels as { slate?: { path?: unknown } } | undefined)
        ?.slate?.path;
      setSlatePath(path != null ? String(path) : null);

      if (refreshCompete) {
        const comp = await postCompete();
        cacheCompetition(comp);
        setCompetition(comp);
        return;
      }
      try {
        const list = await getCandidates();
        if (list && (list.candidate_count as number) > 0) {
          setCompetition(list);
          return;
        }
      } catch {
        /* fall through */
      }
      const cached = readCachedCompetition();
      if (cached) {
        setCompetition(cached);
        return;
      }
      try {
        const comp = await postCompete();
        cacheCompetition(comp);
        setCompetition(comp);
      } catch {
        setCompetition(null);
      }
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "book load failed";
      setError(msg);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const candidates = useMemo(() => parseCandidates(competition), [competition]);
  const portfolioRows = useMemo(() => parsePortfolio(portfolio), [portfolio]);
  const settlementRows = useMemo(
    () => parseSettlements(portfolio),
    [portfolio],
  );
  const settlementPending = settlementRows.filter(
    (r) => r.status.toUpperCase() === "PENDING",
  ).length;
  const settlementTerminal = settlementRows.length - settlementPending;

  const modelEdgeEnabled = Boolean(competition?.model_edge_enabled);
  const modelEdgeCount = candidates.filter(
    (c) => c.strategy_id === "MODEL_PROBABILITY_EDGE",
  ).length;

  const candidateColumns: Column<Candidate>[] = [
    {
      key: "strategy_id",
      header: "Strategy",
      render: (r) => (
        <span className="mono">
          {r.strategy_id || "—"}
          {r.strategy_family ? (
            <span className="muted"> · {r.strategy_family}</span>
          ) : null}
        </span>
      ),
    },
    {
      key: "event_id",
      header: "Event",
      render: (r) => <span className="mono">{r.event_id || "—"}</span>,
    },
    {
      key: "market_id",
      header: "Market",
      render: (r) => <span className="mono">{r.market_id || "—"}</span>,
    },
    {
      key: "selection",
      header: "Selection",
      render: (r) => r.selection || "—",
    },
    {
      key: "score",
      header: "Score",
      align: "right",
      tabular: true,
      render: (r) => fmtNum(r.score),
    },
    {
      key: "confidence",
      header: "Conf",
      align: "right",
      tabular: true,
      render: (r) => fmtNum(r.confidence),
    },
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <AuthorityChip
          label={r.status}
          tone={toneForStatus(r.status)}
          title={r.reason}
        />
      ),
    },
    {
      key: "authority",
      header: "Authority",
      render: (r) => (
        <AuthorityChip label={r.authority} tone={toneForStatus(r.authority)} />
      ),
    },
  ];

  const portfolioColumns: Column<PortfolioRow>[] = [
    {
      key: "entry_id",
      header: "Entry",
      render: (r) => <span className="mono">{r.entry_id}</span>,
    },
    {
      key: "event_id",
      header: "Event",
      render: (r) => <span className="mono">{r.event_id}</span>,
    },
    {
      key: "market_id",
      header: "Market",
      render: (r) => <span className="mono">{r.market_id}</span>,
    },
    {
      key: "selection",
      header: "Selection",
      render: (r) => r.selection,
    },
    {
      key: "paper_stake",
      header: "Paper stake (sim)",
      align: "right",
      tabular: true,
      render: (r) => fmtNum(r.paper_stake, 2),
    },
    {
      key: "expected_value",
      header: "EV (sim)",
      align: "right",
      tabular: true,
      render: (r) => fmtNum(r.expected_value),
    },
    {
      key: "settled_value",
      header: "Settled (sim)",
      align: "right",
      tabular: true,
      render: (r) => fmtNum(r.settled_value, 2),
    },
    {
      key: "result",
      header: "Result",
      render: (r) => (
        <AuthorityChip
          label={r.paper_result}
          tone={toneForStatus(r.paper_result)}
        />
      ),
    },
  ];

  const settlementColumns: Column<SettlementRow>[] = [
    {
      key: "entry_id",
      header: "Entry",
      render: (r) => <span className="mono">{r.entry_id}</span>,
    },
    {
      key: "event_id",
      header: "Event",
      render: (r) => <span className="mono">{r.event_id}</span>,
    },
    {
      key: "selection",
      header: "Selection",
      render: (r) => r.selection,
    },
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <AuthorityChip
          label={r.status}
          tone={toneForStatus(r.status)}
          title={r.reason}
        />
      ),
    },
    {
      key: "pnl",
      header: "PnL",
      align: "right",
      tabular: true,
      render: (r) => fmtNum(r.pnl, 2),
    },
    {
      key: "final_score",
      header: "Score",
      render: (r) => <span className="mono">{r.final_score}</span>,
    },
    {
      key: "result_source",
      header: "Source",
      render: (r) => <span className="mono">{r.result_source}</span>,
    },
  ];

  function toggleRow(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function onPaperSelected() {
    setBusy("paper");
    setError(null);
    setStatusLine(null);
    try {
      const ids = Array.from(selected);
      // Paper simulation only — no real money.
      const result = await postPaper("default", ids);
      setStatusLine(
        `paper sim → ${String(result.status ?? "ok")} · selected=${ids.length}`,
      );
      setSelected(new Set());
      await load(false);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "paper failed";
      setError(msg);
    } finally {
      setBusy(null);
    }
  }

  async function onRefreshCandidates() {
    setBusy("compete");
    setError(null);
    try {
      await load(true);
      setStatusLine("candidates refreshed");
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "refresh failed";
      setError(msg);
    } finally {
      setBusy(null);
    }
  }

  async function onResettle(fetchEspn: boolean) {
    setBusy(fetchEspn ? "settle-espn" : "settle");
    setError(null);
    setStatusLine(null);
    try {
      const result = await postSettle(
        fetchEspn ? { fetch_espn: true } : {},
      );
      const entries = Array.isArray(result.entries) ? result.entries : [];
      const pending = entries.filter(
        (e) =>
          e &&
          typeof e === "object" &&
          String((e as { status?: unknown }).status ?? "").toUpperCase() ===
            "PENDING",
      ).length;
      setStatusLine(
        `settle → ${String(result.status ?? "ok")} · terminal ${entries.length - pending} · pending ${pending}` +
          (fetchEspn ? " · ESPN" : " · fixture"),
      );
      await load(false);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "settle failed";
      setError(msg);
    } finally {
      setBusy(null);
    }
  }

  const competitionStatus = String(competition?.status ?? "—");
  const portfolioStatus = String(portfolio?.status ?? "EMPTY");
  const isFreeFirst = slatePath === "free-first";

  return (
    <>
      <header className="page-header">
        <h1>Paper book</h1>
        <div className="actions-row">
          <AuthorityChip
            label={competitionStatus}
            tone={toneForStatus(competitionStatus)}
          />
          <AuthorityChip
            label={portfolioStatus}
            tone={toneForStatus(portfolioStatus)}
          />
          <AuthorityChip
            label={
              modelEdgeEnabled
                ? `model_edge on · ${modelEdgeCount}`
                : "model_edge off"
            }
            tone={modelEdgeEnabled ? "warn" : "neutral"}
            title="MODEL_PROBABILITY_EDGE loads only when calibration allows — still SHADOW_ONLY, no money"
          />
        </div>
      </header>

      <p className="lede" role="note">
        <strong>Paper book</strong> — advisory candidates only. Ticket stakes and
        PnL are <strong>simulation</strong> scores for advice quality, not real
        money. This is <strong>not</strong> a sportsbook and cannot place wagers.
      </p>

      <section className="section" aria-label="Candidates">
        <div className="section-head">
          <h2 className="section-title">Candidates</h2>
          <div className="actions-row">
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              aria-busy={busy === "compete" || undefined}
              onClick={() => void onRefreshCandidates()}
            >
              {busy === "compete" ? "Refreshing…" : "Refresh candidates"}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy !== null || selected.size === 0}
              aria-busy={busy === "paper" || undefined}
              onClick={() => void onPaperSelected()}
            >
              {busy === "paper"
                ? "Papering…"
                : `Paper selected (${selected.size})`}
            </button>
          </div>
        </div>
        <DataTable
          columns={candidateColumns}
          rows={candidates}
          rowKey={(r) => r.key}
          selectable
          selectedKeys={selected}
          onToggleRow={(key) => toggleRow(key)}
          emptyMessage={
            competition?.reason
              ? `No candidates — ${String(competition.reason)}`
              : "No candidates — run Compete after Ingest"
          }
        />
      </section>

      <section className="section" aria-label="Paper portfolio">
        <h2 className="section-title">Paper portfolio</h2>
        <DataTable
          columns={portfolioColumns}
          rows={portfolioRows}
          rowKey={(r) => r.key}
          emptyMessage="Empty ledger — paper candidates to open tickets"
        />
      </section>

      <section className="section" aria-label="Settlement queue">
        <div className="section-head">
          <h2 className="section-title">Settlement queue</h2>
          <div className="actions-row">
            <AuthorityChip
              label={`pending ${settlementPending}`}
              tone={settlementPending > 0 ? "warn" : "neutral"}
            />
            <AuthorityChip
              label={`terminal ${settlementTerminal}`}
              tone="neutral"
            />
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              aria-busy={busy === "settle" || undefined}
              title="Settle using fixture results.json when a fixture day is loaded."
              onClick={() => void onResettle(false)}
            >
              {busy === "settle" ? "Settling…" : "Settle (fixture)"}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy !== null}
              aria-busy={busy === "settle-espn" || undefined}
              title="Re-settle via ESPN scoreboard finals. Non-final games stay PENDING. No money."
              onClick={() => void onResettle(true)}
            >
              {busy === "settle-espn"
                ? "Settling ESPN…"
                : isFreeFirst
                  ? "Re-settle (ESPN finals)"
                  : "Settle (ESPN finals)"}
            </button>
          </div>
        </div>
        <p className="lede">
          Triage PENDING vs finals. Outcome source shows ESPN_SCOREBOARD or
          FIXTURE — advisory simulation only.
        </p>
        <DataTable
          columns={settlementColumns}
          rows={settlementRows}
          rowKey={(r) => r.key}
          emptyMessage="No settlements yet — paper then Settle from Today or here"
        />
      </section>

      {error && (
        <p className="error-line" role="alert">
          {error}
        </p>
      )}
      {statusLine && !error && (
        <p className="status-line" aria-live="polite">
          {statusLine}
        </p>
      )}
    </>
  );
}
