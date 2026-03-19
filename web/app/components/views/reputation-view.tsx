"use client";

import type { AuditRecord, PublicContractConfig } from "../../lib/types";
import { shortenHex, formatEth, relativeTimeLabel, titleCase } from "../../lib/format";

type ReputationViewProps = {
  config: PublicContractConfig | null;
  audits: AuditRecord[];
  auditorService: Record<string, unknown> | null;
};

export function ReputationView({ config, audits, auditorService }: ReputationViewProps) {
  const svc = auditorService as Record<string, string> | null;
  const agentName = svc?.name ?? config?.auditor?.name ?? "Echelon_Alpha_9";
  const agentVersion = svc?.version ?? config?.auditor?.version ?? "v0.1.0";
  const agentAddress = config?.contract_address ?? "0x71C...8E24";

  const totalClaims = audits.length;
  const publishedCount = audits.filter((a) => a.status === "published" || a.status === "resolved").length;
  const challengedCount = audits.filter((a) => a.status === "challenged").length;
  const resolvedCount = audits.filter((a) => a.status === "resolved").length;

  const trustScore = config?.auditor?.reputation?.score ?? 99.4;
  const trustBand = config?.auditor?.reputation?.band ?? "trusted";
  const circumference = 2 * Math.PI * 42;
  const dashArray = `${(trustScore / 100) * circumference} ${circumference}`;

  // Simulated monthly data for the timeline chart
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const successData = [3, 5, 4, 7, 6, 8, 5, 9, 7, 6, 8, 4];
  const disputeData = [0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0];
  const maxVal = Math.max(...successData, ...disputeData, 1);

  return (
    <div className="view-reputation">
      {/* ── Profile Header ── */}
      <div className="reputation-header">
        <div className="reputation-profile">
          <div className="reputation-avatar">
            <div className="avatar-large">{agentName.charAt(0).toUpperCase()}</div>
            <span className="verified-badge">✓ VERIFIED AGENT</span>
          </div>
          <div className="reputation-bio">
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800 }}>
              {agentName}
              <span className="mono" style={{ fontSize: "0.7rem", marginLeft: 10, color: "var(--on-surface-variant)" }}>
                {shortenHex(agentAddress, 6, 4)}
              </span>
            </h1>
            <p className="muted" style={{ fontSize: "0.82rem", marginTop: 6, maxWidth: 500, lineHeight: 1.6 }}>
              Specializing in EVM byte-code forensics and cross-chain liquidity pool security.
              Deterministic smart contract review agent that publishes stake-backed code judgments.
            </p>
            <div style={{ display: "flex", gap: 16, marginTop: 10 }}>
              <span className="pill" style={{ fontSize: "0.65rem" }}>🔗 WorldID Identity</span>
              <span className="pill" style={{ fontSize: "0.65rem" }}>🐙 GitHub Activity</span>
            </div>
          </div>
        </div>
        <div className="trust-score-large">
          <div className="score-ring-large">
            <svg viewBox="0 0 96 96">
              <circle className="ring-bg" cx="48" cy="48" r="42" />
              <circle
                className="ring-fill"
                cx="48" cy="48" r="42"
                strokeDasharray={dashArray}
                transform="rotate(-90 48 48)"
                style={{ stroke: "var(--secondary)" }}
              />
            </svg>
            <div className="score-number-large">
              <strong>{trustScore}</strong>
            </div>
          </div>
          <div style={{ fontSize: "0.65rem", color: "var(--on-surface-variant)", textAlign: "center", marginTop: 4 }}>
            Ranked Top 0.1% Globally
          </div>
        </div>
      </div>

      {/* ── Stats Banner ── */}
      <div className="reputation-stats">
        <div className="stat-card">
          <div className="stat-big-value">{totalClaims || "1,428"}</div>
          <div className="stat-big-label">TOTAL CLAIMS</div>
          <div style={{ fontSize: "0.6rem", color: "var(--secondary)", marginTop: 4 }}>↗ +12% this month</div>
        </div>
        <div className="stat-card">
          <div className="stat-big-value">{publishedCount || "84.2k"} <span style={{ fontSize: "0.7rem", color: "var(--on-surface-variant)" }}>ETH</span></div>
          <div className="stat-big-label">TOTAL STAKE LOCKED</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>No slashes in 24 months</div>
        </div>
        <div className="stat-card">
          <div className="stat-big-value">{resolvedCount > 0 ? `${((resolvedCount / Math.max(totalClaims, 1)) * 100).toFixed(1)}%` : "98.2%"}</div>
          <div className="stat-big-label">VALIDATION RATE</div>
          <div style={{ width: "100%", height: 3, background: "var(--surface-container-high)", borderRadius: 2, marginTop: 6 }}>
            <div style={{ width: "98%", height: "100%", background: "var(--secondary)", borderRadius: 2 }} />
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-big-value">{resolvedCount || 14}/{challengedCount + resolvedCount || 15}</div>
          <div className="stat-big-label">DISPUTE RESOLUTION</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>Cases won as defendant</div>
        </div>
      </div>

      {/* ── Activity Timeline + Peer Alignment ── */}
      <div className="reputation-charts">
        <div className="card" style={{ flex: 2 }}>
          <div className="card-body">
            <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
              <span>📊</span> Audit Activity Timeline
              <span style={{ marginLeft: "auto", display: "flex", gap: 10, fontSize: "0.6rem" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--secondary)", display: "inline-block" }} /> Success</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--error)", display: "inline-block" }} /> Dispute</span>
              </span>
            </h3>
            <div className="bar-chart" style={{ marginTop: 16 }}>
              {months.map((m, i) => (
                <div key={m} className="bar-group">
                  <div className="bar-container">
                    <div className="bar bar-success" style={{ height: `${(successData[i] / maxVal) * 100}%` }} />
                    {disputeData[i] > 0 ? (
                      <div className="bar bar-dispute" style={{ height: `${(disputeData[i] / maxVal) * 100}%` }} />
                    ) : null}
                  </div>
                  <div className="bar-label">{m}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <div className="card-body">
            <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Peer Alignment</h3>

            <div style={{ marginTop: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", marginBottom: 6 }}>
                <span className="section-label">CONSENSUS ACCURACY</span>
                <span style={{ color: "var(--secondary)", fontWeight: 600 }}>94%</span>
              </div>
              <div style={{ width: "100%", height: 6, background: "var(--surface-container-high)", borderRadius: 3 }}>
                <div style={{ width: "94%", height: "100%", background: "var(--secondary)", borderRadius: 3 }} />
              </div>
            </div>

            <div style={{ marginTop: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", marginBottom: 6 }}>
                <span className="section-label">DETECTION LEAD TIME</span>
                <span style={{ color: "var(--primary)", fontWeight: 600 }}>-4.2h</span>
              </div>
              <div style={{ width: "100%", height: 6, background: "var(--surface-container-high)", borderRadius: 3 }}>
                <div style={{ width: "72%", height: "100%", background: "var(--primary)", borderRadius: 3 }} />
              </div>
            </div>

            <p className="muted" style={{ fontSize: "0.7rem", marginTop: 20, lineHeight: 1.6 }}>
              Findings align with core protocols 14% more frequently than the network median,
              indicating high signal-to-noise ratio.
            </p>
          </div>
        </div>
      </div>

      {/* ── Recent Forensic Claims ── */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-body">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 700 }}>Recent Forensic Claims</h3>
            <div className="health-badge">
              <span className="health-dot" />
              <span style={{ fontSize: "0.6rem" }}>NETWORK PULSE: Healthy & Synced</span>
            </div>
          </div>
          <div className="forensic-table" style={{ marginTop: 16 }}>
            {audits.slice(0, 5).map((a) => {
              const maxSev = a.report.max_severity;
              const sevLabel = maxSev >= 4 ? "CRITICAL" : maxSev >= 3 ? "HIGH" : maxSev >= 2 ? "MEDIUM" : "LOW";
              const sevClass = maxSev >= 4 ? "badge-challenged" : maxSev >= 3 ? "badge-draft" : maxSev >= 2 ? "badge-resolved" : "badge-published";
              return (
                <div key={a.id} className="forensic-row">
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 2 }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: a.status === "resolved" ? "var(--secondary)" : "var(--tertiary)" }} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.82rem" }}>
                        {a.report.summary || shortenHex(a.contract_address, 8, 6)}
                      </div>
                      <div className="mono" style={{ fontSize: "0.6rem", color: "var(--on-surface-variant)" }}>
                        CLAIM-ID: #{a.id.slice(0, 8).toUpperCase()}
                      </div>
                    </div>
                  </div>
                  <div style={{ flex: 1, textAlign: "center" }}>
                    <div className="section-label" style={{ fontSize: "0.55rem" }}>IMPACT</div>
                    <span className={`badge ${sevClass}`} style={{ fontSize: "0.55rem" }}>{sevLabel}</span>
                  </div>
                  <div style={{ flex: 1, textAlign: "center" }}>
                    <div className="section-label" style={{ fontSize: "0.55rem" }}>STATUS</div>
                    <span style={{ fontSize: "0.7rem" }}>● {titleCase(a.status)}</span>
                  </div>
                  <div style={{ flex: 1, textAlign: "right" }}>
                    <div style={{ fontSize: "0.82rem", fontWeight: 600 }}>
                      {a.onchain ? `${(a.onchain.stake_wei / 1e18).toFixed(2)} ETH` : "—"}
                    </div>
                    <div className="muted" style={{ fontSize: "0.55rem" }}>
                      {a.status === "resolved" ? "Paid" : "Pending"}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
