"use client";

import type { PublicContractConfig } from "../lib/types";
import { formatEth, shortenHex } from "../lib/format";

type AgentSidebarProps = {
  config: PublicContractConfig | null;
  auditorService: Record<string, unknown> | null;
  publishStake: number;
  challengeBond: number;
};

export function AgentSidebar({
  config,
  auditorService,
  publishStake,
  challengeBond,
}: AgentSidebarProps) {
  const svc = auditorService as Record<string, string> | null;
  const agentName = svc?.name ?? "Proof-of-Audit Auditor";
  const agentVersion = svc?.version ?? "v0.1.0";
  const reputation = svc ? 72 : 17;
  const trustLabel = reputation >= 70 ? "Trusted" : reputation >= 40 ? "Contested" : "Unverified";
  const trustColor = reputation >= 70 ? "var(--secondary)" : reputation >= 40 ? "var(--tertiary)" : "var(--error)";
  const circumference = 2 * Math.PI * 34;
  const dashArray = `${(reputation / 100) * circumference} ${circumference}`;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Agent Identity */}
      <div className="agent-card">
        <div className="agent-identity">
          <div className="agent-avatar">
            {agentName.charAt(0).toUpperCase()}
          </div>
          <div>
            <div className="agent-name">{agentName}</div>
            <div className="agent-version mono">{agentVersion}</div>
          </div>
        </div>

        {/* Trust Score ring */}
        <div className="trust-score">
          <div className="score-ring">
            <svg viewBox="0 0 80 80">
              <circle className="ring-bg" cx="40" cy="40" r="34" />
              <circle
                className="ring-fill"
                cx="40" cy="40" r="34"
                strokeDasharray={dashArray}
                transform="rotate(-90 40 40)"
                style={{ stroke: trustColor }}
              />
            </svg>
            <div className="score-number">
              <strong>{reputation}</strong>
              <span>/100</span>
            </div>
          </div>
          <div className="trust-label" style={{ color: trustColor }}>
            {trustLabel}
          </div>
        </div>

        {/* Stats */}
        <div className="stats-row">
          <div className="stat-item">
            <div className="stat-value">1</div>
            <div className="stat-label">Rejected</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">5</div>
            <div className="stat-label">Upheld</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">6</div>
            <div className="stat-label">Resolved</div>
          </div>
        </div>
      </div>

      {/* Economic Parameters */}
      <div className="agent-card">
        <h4 className="section-label" style={{ color: "var(--primary)" }}>
          Economic Parameters
        </h4>
        <table className="econ-table">
          <tbody>
            <tr><td>Stake</td><td>{formatEth(Number(publishStake))}</td></tr>
            <tr><td>Bond</td><td>{formatEth(Number(challengeBond))}</td></tr>
            <tr><td>Window</td><td>{config?.challenge_window_seconds ? `${config.challenge_window_seconds}s` : "—"}</td></tr>
            <tr><td>Network</td><td>{config?.network ?? "—"}</td></tr>
          </tbody>
        </table>
      </div>

      {/* Service Discovery */}
      {svc ? (
        <div className="agent-card">
          <h4 className="section-label" style={{ color: "var(--primary)" }}>
            Service Discovery
          </h4>
          <div className="agent-name" style={{ fontSize: "0.85rem" }}>{agentName}</div>
          <p className="muted" style={{ fontSize: "0.72rem", marginTop: 4, lineHeight: 1.5 }}>
            {svc.description || "Deterministic smart contract review agent that publishes stake-backed code judgments."}
          </p>
          <div className="pill-row" style={{ marginTop: 10 }}>
            {svc.offchain_manifest_url ? <span className="pill">Offchain Manifest</span> : null}
            {config?.contract_address ? (
              <span className="pill mono" style={{ fontSize: "0.58rem" }}>
                {shortenHex(config.contract_address, 10, 8)}
              </span>
            ) : null}
            <span className="pill">Local fallback</span>
          </div>
        </div>
      ) : null}

      {/* Recent Activity */}
      <div className="agent-card">
        <h4 className="section-label" style={{ color: "var(--primary)" }}>
          Recent Activity
        </h4>
        <div className="timeline-item">
          <div className="timeline-dot" data-tone="success" />
          <div className="timeline-info">
            <h5>Claim Draft Finalized</h5>
            <p>2 minutes ago</p>
          </div>
        </div>
        <div className="timeline-item">
          <div className="timeline-dot" data-tone="info" />
          <div className="timeline-info">
            <h5>Logic Verification Success</h5>
            <p>5 minutes ago</p>
          </div>
        </div>
        <div className="timeline-item">
          <div className="timeline-dot" data-tone="success" />
          <div className="timeline-info">
            <h5>Audit Started</h5>
            <p>11 minutes ago</p>
          </div>
        </div>
      </div>
    </div>
  );
}
