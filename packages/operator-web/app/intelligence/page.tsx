"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AuthorityChip, toneForStatus } from "@/components/AuthorityChip";
import {
  ApiError,
  getV06Books,
  getV06DevigCalibrations,
  getV06Health,
  getV06Models,
  type Json,
} from "@/lib/api";

type Domain = "bookmaker" | "context" | "dependency" | "structural" | "promotions";
type IntelligenceState = Record<Domain, Json | null> & {
  books: Json | null;
  models: Json | null;
  calibrations: Json | null;
};

const EMPTY: IntelligenceState = {
  bookmaker: null,
  context: null,
  dependency: null,
  structural: null,
  promotions: null,
  books: null,
  models: null,
  calibrations: null,
};

const DOMAINS: Array<{ id: Domain; index: string; label: string; description: string }> = [
  { id: "bookmaker", index: "01", label: "Market memory", description: "Immutable observations and bookmaker reconstruction." },
  { id: "context", index: "02", label: "Context states", description: "Player, travel, recovery, coaching and venue evidence." },
  { id: "dependency", index: "03", label: "Joint contracts", description: "Inspectable dependencies and parlay probability models." },
  { id: "structural", index: "04", label: "Synthesis", description: "Deterministic verdict packets with normal PASS outcomes." },
];

function value(record: Json | null, key: string): unknown {
  return record?.[key];
}

function count(record: Json | null, ...keys: string[]): number {
  for (const key of keys) {
    const candidate = value(record, key);
    if (typeof candidate === "number" && Number.isFinite(candidate)) return candidate;
    if (Array.isArray(candidate)) return candidate.length;
  }
  return 0;
}

function list(record: Json | null, key: string): unknown[] {
  const candidate = value(record, key);
  return Array.isArray(candidate) ? candidate : [];
}

function statusOf(record: Json | null): string {
  return String(record?.status ?? "NOT_COMPUTABLE");
}

export default function IntelligencePage() {
  const [data, setData] = useState<IntelligenceState>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDomain, setSelectedDomain] = useState<Domain>("bookmaker");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [bookmaker, context, dependency, structural, promotions, books, models, calibrations] = await Promise.all([
        getV06Health("bookmaker"),
        getV06Health("context"),
        getV06Health("dependency"),
        getV06Health("structural"),
        getV06Health("promotions"),
        getV06Books(),
        getV06Models(),
        getV06DevigCalibrations(),
      ]);
      setData({ bookmaker, context, dependency, structural, promotions, books, models, calibrations });
    } catch (cause) {
      setData(EMPTY);
      setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : "Intelligence surfaces unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const bookCount = list(data.books, "books").length;
  const snapshotCount = count(data.bookmaker, "snapshot_count");
  const contextCount = count(data.context, "observation_count");
  const graphCount = count(data.dependency, "observation_count");
  const analysisCount = count(data.structural, "analysis_count");
  const promotionCount = count(data.promotions, "devig_promotion_count") + count(data.promotions, "model_promotion_count");
  const modelCount = list(data.models, "records").length;
  const calibrationCount = list(data.calibrations, "records").length;
  const evidenceTotal = snapshotCount + contextCount + graphCount + analysisCount;

  const selected = data[selectedDomain];
  const selectedIssues = list(selected, "integrity_issues").map(String);
  const readiness = useMemo(() => {
    const statuses = DOMAINS.map((domain) => statusOf(data[domain.id]));
    return statuses.every((status) => status === "PASS") ? "EVIDENCE HEALTHY" : "EVIDENCE INCOMPLETE";
  }, [data]);

  return (
    <div className="intel-page">
      <header className="intel-hero">
        <div className="intel-hero-copy">
          <div className="eyebrow"><span>V0.6</span> BOOKMAKER INTELLIGENCE</div>
          <h1>Read the price.<br /><em>Not the story.</em></h1>
          <p>
            A forensic workspace for fair bookmaker probabilities, player distributions,
            contextual transforms and joint parlay contracts. Every conclusion remains
            evidence-bound and advisory-only.
          </p>
          <div className="intel-hero-actions">
            <button className="btn btn-primary" type="button" onClick={() => void refresh()} disabled={loading} aria-busy={loading || undefined}>
              {loading ? "Reading ledgers…" : "Refresh evidence"}
            </button>
            <AuthorityChip label="SHADOW_ONLY" tone="neutral" />
            <AuthorityChip label="NO EXECUTION" tone="ok" />
          </div>
        </div>
        <div className="intel-orbit" aria-label={`${evidenceTotal} evidence observations`}>
          <div className="orbit-ring orbit-ring-a" />
          <div className="orbit-ring orbit-ring-b" />
          <div className="orbit-crosshair" />
          <div className="orbit-core">
            <strong>{evidenceTotal.toLocaleString()}</strong>
            <span>evidence<br />records</span>
          </div>
          <span className="orbit-label orbit-label-top">OBSERVATION</span>
          <span className="orbit-label orbit-label-right">DERIVATION</span>
          <span className="orbit-label orbit-label-bottom">VERDICT</span>
        </div>
      </header>

      {error && <p className="intel-alert" role="alert"><span>API OFFLINE</span>{error}</p>}

      <section className="intel-metrics" aria-label="Evidence overview">
        <Metric label="Books observed" value={bookCount} note="first-class identities" />
        <Metric label="Market snapshots" value={snapshotCount} note="append-only memory" />
        <Metric label="Context states" value={contextCount} note="provenance linked" />
        <Metric label="Dependency graphs" value={graphCount} note="joint, not multiplied" />
        <Metric label="Shadow promotions" value={promotionCount} note={`${modelCount} models · ${calibrationCount} calibrations`} />
      </section>

      <section className="intel-workbench">
        <div className="intel-section-head">
          <div>
            <div className="eyebrow">SYSTEM TOPOLOGY</div>
            <h2>Evidence pipeline</h2>
          </div>
          <AuthorityChip label={readiness} tone={readiness === "EVIDENCE HEALTHY" ? "ok" : "warn"} />
        </div>

        <div className="domain-grid">
          {DOMAINS.map((domain) => {
            const packet = data[domain.id];
            const active = selectedDomain === domain.id;
            return (
              <button key={domain.id} type="button" className={`domain-card${active ? " is-active" : ""}`} onClick={() => setSelectedDomain(domain.id)} aria-pressed={active}>
                <span className="domain-index">{domain.index}</span>
                <span className="domain-status"><i className={`status-dot status-${toneForStatus(statusOf(packet))}`} />{statusOf(packet)}</span>
                <strong>{domain.label}</strong>
                <small>{domain.description}</small>
                <span className="domain-count">{domainCount(domain.id, data).toLocaleString()} <i>packets</i></span>
              </button>
            );
          })}
        </div>

        <div className="intel-inspector">
          <div className="inspector-rail">
            <span>SELECTED DOMAIN</span>
            <strong>{selectedDomain.toUpperCase()}</strong>
          </div>
          <div className="inspector-main">
            <div className="inspector-head">
              <div>
                <span className="eyebrow">INTEGRITY READOUT</span>
                <h3>{DOMAINS.find((domain) => domain.id === selectedDomain)?.label}</h3>
              </div>
              <AuthorityChip label={statusOf(selected)} tone={toneForStatus(statusOf(selected))} />
            </div>
            <dl className="signal-list">
              {signalRows(selectedDomain, selected).map(([label, signalValue]) => (
                <div key={label}><dt>{label}</dt><dd>{signalValue}</dd></div>
              ))}
            </dl>
            <div className="integrity-note">
              <span>INTEGRITY</span>
              <p>{selectedIssues.length ? selectedIssues.join(" · ") : "No local ledger integrity issues reported."}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="intel-products" aria-label="Intelligence products">
        <div className="intel-section-head">
          <div><div className="eyebrow">OPERATOR SURFACES</div><h2>Four views, one contract</h2></div>
          <span className="meta-line">OBSERVATION → DERIVATION → VERDICT</span>
        </div>
        <div className="product-grid">
          <Product index="A" title="Market Radar" copy="Cross-book consensus, residuals, pressure and information age without inventing causal stories." accent="blue" />
          <Product index="B" title="House Curve" copy="Monotonic prop ladders expose tail tax, discontinuities and book-to-reality conflict." accent="green" />
          <Product index="C" title="Parlay X-Ray" copy="Joint probability and dependency charges replace naïve multiplication." accent="amber" />
          <Product index="D" title="Parlay Surgery" copy="Marginal leg value identifies destructive additions before they reach paper simulation." accent="red" />
        </div>
      </section>

      <footer className="intel-contract">
        <span className="contract-mark">HS</span>
        <div><strong>Know when not to form a recommendation.</strong><p>PASS and NOT_COMPUTABLE are successful system outcomes.</p></div>
        <div className="contract-code">capital_authority=false<br />execution_authority=false</div>
      </footer>
    </div>
  );
}

function domainCount(domain: Domain, data: IntelligenceState): number {
  if (domain === "bookmaker") return count(data.bookmaker, "snapshot_count");
  if (domain === "context") return count(data.context, "observation_count", "derivation_count");
  if (domain === "dependency") return count(data.dependency, "observation_count", "analysis_count");
  return count(data.structural, "observation_count", "analysis_count");
}

function signalRows(domain: Domain, packet: Json | null): Array<[string, string]> {
  if (!packet) return [["Packet", "NOT_COMPUTABLE"], ["Reason", "No evidence packet loaded"]];
  const common: Array<[string, string]> = [["Schema", String(packet.schema_version ?? "—")], ["Status", statusOf(packet)]];
  if (domain === "bookmaker") return [...common, ["Snapshots", String(packet.snapshot_count ?? 0)], ["Append only", String(packet.append_only ?? true)]];
  if (domain === "context") return [...common, ["Observations", String(packet.observation_count ?? 0)], ["Derivations", String(packet.derivation_count ?? 0)], ["Recorded-at gate", String(packet.recorded_at_gate ?? false)]];
  if (domain === "dependency") return [...common, ["Graphs", String(packet.observation_count ?? 0)], ["Analyses", String(packet.analysis_count ?? 0)], ["Unknown policy", String(packet.unknown_dependency_policy ?? "NOT_COMPUTABLE")]];
  return [...common, ["Observations", String(packet.observation_count ?? 0)], ["Verdicts", String(packet.analysis_count ?? 0)], ["Authority", String(packet.authority ?? "SHADOW_ONLY")]];
}

function Metric({ label, value: metricValue, note }: { label: string; value: number; note: string }) {
  return <div className="intel-metric"><span>{label}</span><strong>{metricValue.toLocaleString()}</strong><small>{note}</small></div>;
}

function Product({ index, title, copy, accent }: { index: string; title: string; copy: string; accent: string }) {
  return <article className={`product-card product-${accent}`}><span>{index}</span><h3>{title}</h3><p>{copy}</p><i>SHADOW SURFACE</i></article>;
}
