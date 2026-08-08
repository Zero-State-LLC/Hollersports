/**
 * Browser client for HollerSports operator API.
 * All paths are same-origin `/v1/*` and rewritten to :8000 by next.config.
 */

export type Json = Record<string, unknown>;

const PUBLIC_API_ORIGIN = (process.env.NEXT_PUBLIC_HOLLER_API_ORIGIN ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function parseBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function request<T = Json>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const target = PUBLIC_API_ORIGIN && path.startsWith("/") ? `${PUBLIC_API_ORIGIN}${path}` : path;
  const res = await fetch(target, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  const body = await parseBody(res);
  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(detail || `HTTP ${res.status}`, res.status, body);
  }
  return body as T;
}

export function getDashboard() {
  return request<Json>("/v1/dashboard");
}

export function getPortfolio() {
  return request<Json>("/v1/portfolio");
}

export function getPromotion() {
  return request<Json>("/v1/promotion");
}

export function getReliability() {
  return request<Json>("/v1/reliability");
}

/** Append-only reliability ledger snapshots (oldest-first within window). */
export function getReliabilityHistory(limit = 20) {
  const q = new URLSearchParams({
    history: "1",
    limit: String(Math.max(1, Math.min(limit, 200))),
  });
  return request<Json>(`/v1/reliability?${q.toString()}`);
}

export function getHealth() {
  return request<Json>("/v1/health");
}

/** V0.6 evidence-bound intelligence surfaces. Read-only and advisory-only. */
export function getV06Books() {
  return request<Json>("/v1/books");
}

export function getV06Health(domain: "bookmaker" | "context" | "dependency" | "structural" | "promotions") {
  return request<Json>(`/v1/health/${domain}`);
}

export function getV06Models() {
  return request<Json>("/v1/models");
}

export function getV06DevigCalibrations() {
  return request<Json>("/v1/calibration/devig");
}

export function postIngest(fixture = "day001") {
  return request<Json>("/v1/runs/ingest", {
    method: "POST",
    body: JSON.stringify({ fixture }),
  });
}

export function postCompete(opts?: {
  allow_forecast_weighting?: boolean;
  reliability_status?: string;
  /** Derive reliability from settlements (evidence ladder). Default true when allowing model edge. */
  use_auto_calibration?: boolean;
}) {
  const allow = Boolean(opts?.allow_forecast_weighting);
  const useAuto =
    opts?.use_auto_calibration ?? allow; /* auto when enabling model edge */
  return request<Json>("/v1/runs/compete", {
    method: "POST",
    body: JSON.stringify({
      allow_forecast_weighting: allow,
      use_auto_calibration: useAuto,
      // Manual override path when auto is off
      reliability_status: allow
        ? opts?.reliability_status ?? "RELIABLE"
        : opts?.reliability_status ?? "UNRELIABLE",
    }),
  });
}

export function getCalibration(allowForecastWeighting = false) {
  const q = new URLSearchParams({
    allow_forecast_weighting: allowForecastWeighting ? "1" : "0",
  });
  return request<Json>(`/v1/calibration?${q.toString()}`);
}

export function postPaper(portfolioId = "default", candidateIds?: string[]) {
  return request<Json>("/v1/runs/paper", {
    method: "POST",
    body: JSON.stringify({
      portfolio_id: portfolioId,
      ...(candidateIds?.length ? { candidate_ids: candidateIds } : {}),
    }),
  });
}

export function postSettle(opts?: {
  espn_raw?: Json;
  leagues?: string[];
  results?: Json[];
  fetch_espn?: boolean;
}) {
  const body: Record<string, unknown> = {};
  if (opts?.espn_raw) body.espn_raw = opts.espn_raw;
  if (opts?.leagues?.length) body.leagues = opts.leagues;
  if (opts?.results?.length) body.results = opts.results;
  if (opts?.fetch_espn) body.fetch_espn = true;
  return request<Json>("/v1/runs/settle", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function postFullDay(fixture = "day001") {
  return request<Json>("/v1/runs/full-day", {
    method: "POST",
    body: JSON.stringify({ fixture }),
  });
}

/** Live free-first observation (may hit network; no money). Prefer fixture day for demos. */
export function postFreeFirst(opts?: {
  espn_only?: boolean;
  odds_only?: boolean;
  auto_compete?: boolean;
  /** Day-one leagues; omit for all. Example: ["NBA","NFL"]. */
  leagues?: string[];
}) {
  const body: Record<string, unknown> = {
    espn_only: opts?.espn_only ?? false,
    odds_only: opts?.odds_only ?? false,
    auto_compete: opts?.auto_compete ?? true,
  };
  if (opts?.leagues && opts.leagues.length > 0) {
    body.leagues = opts.leagues;
  }
  return request<Json>("/v1/runs/free-first", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Closed free-first day → paper → ESPN settle → calibration bank (advisory only). */
export function postFreeFirstDay(opts?: {
  espn_only?: boolean;
  odds_only?: boolean;
  fetch_espn_finals?: boolean;
  leagues?: string[];
  paper_top_n?: number;
}) {
  const body: Record<string, unknown> = {
    espn_only: opts?.espn_only ?? false,
    odds_only: opts?.odds_only ?? false,
    fetch_espn_finals: opts?.fetch_espn_finals ?? true,
  };
  if (opts?.leagues && opts.leagues.length > 0) {
    body.leagues = opts.leagues;
  }
  if (opts?.paper_top_n != null) {
    body.paper_top_n = opts.paper_top_n;
  }
  return request<Json>("/v1/runs/free-first-day", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getCandidates() {
  return request<Json>("/v1/candidates");
}

/** Track F ML status (ensemble path / last train). Advisory research tooling. */
export function getMlStatus() {
  return request<Json>("/v1/ml/status");
}

/** Train baseline ensemble from fixture days (offline; no money). */
export function postMlTrain(opts?: {
  train_fixtures?: string[];
  val_fixtures?: string[];
  seed?: number;
  prefer_sklearn?: boolean;
}) {
  return request<Json>("/v1/ml/train", {
    method: "POST",
    body: JSON.stringify({
      train_fixtures: opts?.train_fixtures ?? ["day001", "day002"],
      val_fixtures: opts?.val_fixtures,
      seed: opts?.seed ?? 42,
      prefer_sklearn: opts?.prefer_sklearn ?? false,
    }),
  });
}

/**
 * Annotate last ingest markets with model_probability.
 * Fail closed if no ensemble. Optional auto_compete + model-edge gates.
 */
export function postMlAnnotate(opts?: {
  ensemble_path?: string;
  ev_threshold?: number;
  auto_compete?: boolean;
  allow_forecast_weighting?: boolean;
  reliability_status?: string;
  use_auto_calibration?: boolean;
}) {
  const body: Record<string, unknown> = {
    ev_threshold: opts?.ev_threshold ?? 0.03,
    auto_compete: opts?.auto_compete ?? false,
    allow_forecast_weighting: opts?.allow_forecast_weighting ?? false,
    reliability_status: opts?.reliability_status ?? "UNRELIABLE",
    use_auto_calibration: opts?.use_auto_calibration ?? false,
  };
  if (opts?.ensemble_path) body.ensemble_path = opts.ensemble_path;
  return request<Json>("/v1/ml/annotate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Model card for last ensemble (metrics + markdown). */
export function getMlModelCard(ensemble_path?: string) {
  const q = ensemble_path
    ? `?ensemble_path=${encodeURIComponent(ensemble_path)}`
    : "";
  return request<Json>(`/v1/ml/model-card${q}`);
}

/** Axial temporal stub on last ingest (stdlib placeholder, not neural). */
export function postMlAxialStub() {
  return request<Json>("/v1/ml/axial-stub", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

/** Advisory retrain proposal (never auto-trains). */
export function postMlRetrainCheck(opts?: {
  ensemble_path?: string;
  eval_fixtures?: string[];
  brier_degrade?: number;
  min_labeled?: number;
}) {
  return request<Json>("/v1/ml/retrain-check", {
    method: "POST",
    body: JSON.stringify({
      ensemble_path: opts?.ensemble_path,
      eval_fixtures: opts?.eval_fixtures ?? ["day001", "day002", "day003"],
      brier_degrade: opts?.brier_degrade ?? 0.01,
      min_labeled: opts?.min_labeled ?? 8,
    }),
  });
}

/**
 * Gated retrain apply — requires confirm=true.
 * Default require_suggestion=true (last check must be RETRAIN_SUGGESTED).
 */
export function postMlRetrainApply(opts: {
  confirm: boolean;
  require_suggestion?: boolean;
  train_fixtures?: string[];
  seed?: number;
}) {
  return request<Json>("/v1/ml/retrain-apply", {
    method: "POST",
    body: JSON.stringify({
      confirm: opts.confirm,
      require_suggestion: opts.require_suggestion ?? true,
      train_fixtures: opts.train_fixtures ?? ["day001", "day002", "day003"],
      seed: opts.seed ?? 42,
    }),
  });
}

/** RSS lexicon sentiment on last ingest (inject XML or opt-in fetch). */
export function postMlRssSentiment(opts?: {
  fetch?: boolean;
  feed_xml?: string;
  feed_urls?: string[];
  apply_to_ingest?: boolean;
}) {
  return request<Json>("/v1/ml/sentiment/rss", {
    method: "POST",
    body: JSON.stringify({
      fetch: opts?.fetch ?? false,
      feed_xml: opts?.feed_xml,
      feed_urls: opts?.feed_urls,
      apply_to_ingest: opts?.apply_to_ingest ?? true,
    }),
  });
}

/** Session-backed last competition packet (fallback if GET /candidates empty). */
const COMPETE_KEY = "holler.operator.lastCompetition";

export function cacheCompetition(packet: Json): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(COMPETE_KEY, JSON.stringify(packet));
  } catch {
    /* quota / private mode */
  }
}

export function readCachedCompetition(): Json | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(COMPETE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Json;
  } catch {
    return null;
  }
}

export function candidateKey(c: {
  strategy_id?: unknown;
  market_id?: unknown;
  selection?: unknown;
}): string {
  return `${String(c.strategy_id ?? "")}|${String(c.market_id ?? "")}|${String(c.selection ?? "")}`;
}

export function fieldOrDash(
  value: unknown,
  reason = "not on dashboard packet",
): { text: string; reason?: string } {
  if (value === null || value === undefined || value === "") {
    return { text: "—", reason };
  }
  if (typeof value === "object") {
    try {
      return { text: JSON.stringify(value) };
    } catch {
      return { text: "—", reason: "unserializable" };
    }
  }
  return { text: String(value) };
}
