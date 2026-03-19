"use client";

import type { AuditRecord } from "../../lib/types";
import { challengePathSummary, shortenHex, titleCase, relativeTimeLabel, formatEth } from "../../lib/format";

type DisputedViewProps = {
  audit: AuditRecord;
  allAudits: AuditRecord[];
  onSelect: (a: AuditRecord) => void;
};

export function DisputedView({ audit, allAudits, onSelect }: DisputedViewProps) {
  const relatedClaims = allAudits
    .filter((a) => a.id !== audit.id && a.contract_address === audit.contract_address)
    .slice(0, 3);
  const confidenceLabel = audit.report.confidence ? titleCase(audit.report.confidence) : "Unavailable";
  const resolutionPath = audit.challenge?.resolution_path
    ? titleCase(audit.challenge.resolution_path)
    : "Unavailable";
  const resolutionMeta = audit.challenge?.verification_status
    ? titleCase(audit.challenge.verification_status)
    : audit.challenge?.verifier ?? "Verifier unavailable";

  return (
    <div className="view-disputed">
      {/* ── Header ── */}
      <div className="claim-banner">
        <div className="claim-banner-left">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="mono" style={{ fontSize: "0.72rem", color: "var(--on-surface-variant)" }}>
              Claims / Claim #{audit.id.slice(0, 8).toUpperCase()}
            </span>
          </div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 800, marginTop: 8, display: "flex", alignItems: "center", gap: 14 }}>
            Audit Claim #{audit.id.slice(0, 8).toUpperCase()}
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ width: 8, height: 8, background: "var(--secondary)", borderRadius: "50%" }} />
            </span>
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
            <span className="muted" style={{ fontSize: "0.78rem" }}>
              Published smart contract audit claim for <code className="mono" style={{ fontSize: "0.72rem" }}>{shortenHex(audit.contract_address, 12, 8)}</code>
            </span>
            <span className="badge badge-challenged">{audit.status.toUpperCase()}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {audit.onchain?.publish_tx_url ? (
            <a href={audit.onchain.publish_tx_url} target="_blank" rel="noopener noreferrer" className="btn-outline">
              ↗ View on Etherscan
            </a>
          ) : null}
          <button type="button" className="cta-gradient" style={{ padding: "10px 20px", fontSize: "0.78rem" }}>
            🔐 Submit Evidence
          </button>
        </div>
      </div>

      {/* ── Stats Row ── */}
      <div className="reputation-stats" style={{ marginTop: 20 }}>
        <div className="stat-card">
          <div className="stat-big-label">TOTAL STAKE</div>
          <div className="stat-big-value">{audit.onchain ? formatEth(audit.onchain.stake_wei) : "—"}</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>
            {audit.onchain?.network ?? "On-chain details unavailable"}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-big-label">DISPUTES</div>
          <div className="stat-big-value">{audit.challenge ? "01 Active" : "00"}</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>
            {audit.challenge ? `Last challenged ${relativeTimeLabel(audit.challenge.submitted_at)}` : "—"}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-big-label">CONFIDENCE SCORE</div>
          <div className="stat-big-value mono">{confidenceLabel}</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>
            {audit.report.finding_count} findings in the published report
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-big-label">RESOLUTION PATH</div>
          <div className="stat-big-value" style={{ fontSize: "1rem" }}>{resolutionPath}</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>{resolutionMeta}</div>
        </div>
      </div>

      {/* ── Two-column: Findings + On-chain Details ── */}
      <div className="published-grid" style={{ marginTop: 24 }}>
        {/* Left: Audit Report Findings */}
        <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
          <div className="card">
            <div className="card-body">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h2 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Audit Report Findings</h2>
                <button type="button" className="btn-outline" style={{ fontSize: "0.7rem", padding: "6px 12px" }}>
                  ⬇ PDF Report
                </button>
              </div>

              {audit.report.findings.slice(0, 4).map((f, i) => {
                const sev = (f.severity || "info").toLowerCase();
                const icon = sev === "critical" ? "🔴" : sev === "high" ? "🟠" : sev === "medium" ? "🟡" : "🟢";
                const badgeClass = sev === "critical" ? "badge-challenged" : sev === "high" ? "badge-draft" : sev === "medium" ? "badge-resolved" : "badge-published";
                return (
                  <div key={i} className="finding-detail" style={{ marginTop: 20, padding: 18, background: "var(--surface-container-low)", borderRadius: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                      <span style={{ fontSize: "1.2rem" }}>{icon}</span>
                      <h4 style={{ fontSize: "0.88rem", fontWeight: 700 }}>
                        F-{String(i + 1).padStart(2, "0")}: {f.title}
                      </h4>
                    </div>
                    <p style={{ fontSize: "0.78rem", color: "var(--on-surface-variant)", lineHeight: 1.6 }}>
                      {f.description}
                    </p>
                    <div style={{ display: "flex", gap: 10, marginTop: 10, alignItems: "center" }}>
                      <span className={`badge ${badgeClass}`} style={{ fontSize: "0.55rem" }}>
                        {titleCase(sev)} RISK
                      </span>
                      <span className="mono" style={{ fontSize: "0.6rem", color: "var(--on-surface-variant)" }}>
                        Hash: {shortenHex(f.finding_id, 6, 4)}
                      </span>
                    </div>
                  </div>
                );
              })}

              {audit.report.findings.length > 4 ? (
                <button type="button" className="btn-outline" style={{ width: "100%", marginTop: 16, justifyContent: "center" }}>
                  Show {audit.report.findings.length - 4} More Findings
                </button>
              ) : null}
            </div>
          </div>

          {/* Active Challenges Table */}
          {audit.challenge ? (
            <div className="card">
              <div className="card-body">
                <h2 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Active Challenges</h2>
                <div className="challenge-table" style={{ marginTop: 16 }}>
                  <div className="challenge-table-header">
                    <span>CHALLENGER</span>
                    <span>STAKE AMOUNT</span>
                    <span>STATUS</span>
                    <span>EVIDENCE</span>
                  </div>
                  <div className="challenge-table-row">
                    <span className="mono" style={{ fontSize: "0.72rem" }}>
                      {shortenHex(audit.challenge.challenger, 6, 4)}
                    </span>
                    <span>{audit.challenge.challenge_bond_wei ? formatEth(audit.challenge.challenge_bond_wei) : "—"}</span>
                    <span style={{ color: audit.challenge.status === "resolved" ? "var(--secondary)" : "var(--tertiary)" }}>
                      ● {titleCase(audit.challenge.status ?? "pending")}
                    </span>
                    <a href={audit.challenge.proof_uri} className="evidence-link" target="_blank" rel="noopener noreferrer">
                      View evidence
                    </a>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Right: On-Chain Details + Related Claims */}
        <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
          <div className="card">
            <div className="card-body">
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>On-Chain Details</h3>

              <div style={{ marginTop: 16 }}>
                <div className="hash-label">TRANSACTION HASH</div>
                <div className="hash-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <code className="mono" style={{ fontSize: "0.7rem" }}>
                    {audit.onchain?.publish_tx_hash ? shortenHex(audit.onchain.publish_tx_hash, 10, 6) : "Pending..."}
                  </code>
                  <span style={{ cursor: "pointer", opacity: 0.6 }}>📋</span>
                </div>
              </div>

              <div style={{ marginTop: 16 }}>
                <div className="hash-label">CHAIN ID</div>
                <div className="mono" style={{ fontSize: "0.88rem", fontWeight: 600, marginTop: 4 }}>
                  {audit.onchain?.chain_id ?? "—"}
                </div>
              </div>

              <div style={{ marginTop: 16 }}>
                <div className="hash-label">CONTRACT ORIGIN</div>
                <div className="mono" style={{ fontSize: "0.78rem", marginTop: 4 }}>
                  {audit.onchain?.network ?? "Unavailable"}
                </div>
              </div>

              <div style={{ marginTop: 20, display: "flex", alignItems: "center", gap: 8, color: "var(--secondary)" }}>
                <span>✅</span>
                <strong style={{ fontSize: "0.82rem" }}>Immutable Commitment</strong>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-body">
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Resolution Path</h3>
              <div style={{ marginTop: 12, display: "flex", alignItems: "flex-start", gap: 10 }}>
                <span style={{ fontSize: "1.2rem" }}>⚡</span>
                <div>
                  <p style={{ fontSize: "0.82rem", lineHeight: 1.6 }}>
                    {challengePathSummary(audit)}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Related Claims */}
          <div className="card">
            <div className="card-body">
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Related Claims</h3>
              {relatedClaims.map((rc) => (
                <button
                  key={rc.id}
                  type="button"
                  className="related-claim-row"
                  onClick={() => onSelect(rc)}
                  style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", padding: "12px 0", borderBottom: "1px solid rgba(67,70,85,0.15)", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--on-surface)" }}>
                      {rc.report.summary || `Claim #${rc.id.slice(0, 6).toUpperCase()}`}
                    </div>
                    <div className="muted" style={{ fontSize: "0.65rem" }}>
                      {rc.report.summary ? shortenHex(rc.contract_address, 8, 6) : ""} · {rc.report.finding_count} Findings
                    </div>
                  </div>
                  <span className={`badge badge-${rc.status === "published" ? "published" : rc.status === "challenged" ? "challenged" : "resolved"}`} style={{ fontSize: "0.55rem" }}>
                    {rc.status.toUpperCase()}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
