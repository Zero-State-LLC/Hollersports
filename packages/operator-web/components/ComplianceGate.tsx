"use client";

import { useEffect, useState, type ReactNode } from "react";

/** localStorage key — bump suffix if the acknowledgment text materially changes. */
export const COMPLIANCE_ACK_KEY = "hollersports.compliance.ack.v1";

type ComplianceGateProps = {
  children: ReactNode;
};

/**
 * First-run gate for App Store / distribution scrutiny:
 * age floor, jurisdiction awareness, paper-only / no real-money acknowledgment.
 * Local operator tool — acknowledgment is client-side only.
 */
export function ComplianceGate({ children }: ComplianceGateProps) {
  const [ready, setReady] = useState(false);
  const [acked, setAcked] = useState(false);
  const [ageOk, setAgeOk] = useState(false);
  const [jurisdictionOk, setJurisdictionOk] = useState(false);
  const [paperOk, setPaperOk] = useState(false);

  useEffect(() => {
    try {
      setAcked(window.localStorage.getItem(COMPLIANCE_ACK_KEY) === "1");
    } catch {
      setAcked(false);
    }
    setReady(true);
  }, []);

  function confirm() {
    if (!ageOk || !jurisdictionOk || !paperOk) return;
    try {
      window.localStorage.setItem(COMPLIANCE_ACK_KEY, "1");
    } catch {
      /* private mode — still allow session use after explicit confirm */
    }
    setAcked(true);
  }

  if (!ready) {
    return (
      <div className="compliance-gate" role="status" aria-live="polite">
        <p className="mono">Loading…</p>
      </div>
    );
  }

  if (acked) {
    return <>{children}</>;
  }

  const canContinue = ageOk && jurisdictionOk && paperOk;

  return (
    <div className="compliance-gate" role="dialog" aria-modal="true" aria-labelledby="compliance-title">
      <div className="compliance-card panel">
        <p className="eyebrow mono">Before you operate</p>
        <h1 id="compliance-title">HollerSports is paper-only</h1>
        <p className="lede">
          This workbench scores <strong>advisory</strong> candidates and runs{" "}
          <strong>paper simulation</strong> to measure advice quality. It is{" "}
          <strong>not</strong> a sportsbook, wallet, or wager placement system.
        </p>
        <ul className="compliance-list">
          <li>No real money · no deposits · no book placement</li>
          <li>Stake, bankroll, PnL, and ROI fields are <strong>simulation metrics</strong></li>
          <li>Any real-world betting is outside this software and your responsibility</li>
        </ul>
        <label className="compliance-check">
          <input
            type="checkbox"
            checked={ageOk}
            onChange={(e) => setAgeOk(e.target.checked)}
          />
          <span>
            I am at least <strong>18</strong> (or <strong>21</strong> where sports
            wagering laws require it), and this product is not for children.
          </span>
        </label>
        <label className="compliance-check">
          <input
            type="checkbox"
            checked={jurisdictionOk}
            onChange={(e) => setJurisdictionOk(e.target.checked)}
          />
          <span>
            I understand sports wagering laws vary by jurisdiction and I am
            responsible for legal compliance if I bet elsewhere.
          </span>
        </label>
        <label className="compliance-check">
          <input
            type="checkbox"
            checked={paperOk}
            onChange={(e) => setPaperOk(e.target.checked)}
          />
          <span>
            I understand HollerSports is <strong>advisory / PAPER_SIM only</strong> and
            does not guarantee predictive accuracy or profits.
          </span>
        </label>
        <div className="actions-row compliance-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canContinue}
            onClick={confirm}
          >
            Enter workbench
          </button>
        </div>
        <p className="compliance-foot mono">
          Legal drafts · docs/legal · App Store readiness · docs/APP_STORE_READINESS.md
        </p>
      </div>
    </div>
  );
}
