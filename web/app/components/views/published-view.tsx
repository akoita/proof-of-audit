"use client";

import type { AuditRecord } from "../../lib/types";
import { shortenHex, submissionTargetLabel, titleCase, relativeTimeLabel } from "../../lib/format";

type PublishedViewProps = {
  audit: AuditRecord;
  allAudits: AuditRecord[];
  onSelect: (a: AuditRecord) => void;
};

export function PublishedView({ audit, allAudits, onSelect }: PublishedViewProps) {
  const relatedClaims = allAudits
    .filter((a) => a.id !== audit.id && a.contract_address === audit.contract_address)
    .slice(0, 3);
  const reputation = audit.agent?.reputation
    ? `${audit.agent.reputation.score}/100 ${titleCase(audit.agent.reputation.band)}`
    : "Unavailable";
  const resolutionPath = audit.challenge?.resolution_path
    ? titleCase(audit.challenge.resolution_path)
    : "Not opened yet";
  const resolutionSummary = audit.challenge
    ? audit.challenge.verification_summary ??
      audit.challenge.verification_detail ??
      `${titleCase(audit.challenge.status)} via ${audit.challenge.verifier}`
    : "Resolution path is determined when a challenge is opened.";

  return (
    <div className="view-published">
      {/* ── Header banner ── */}
      <div className="claim-banner">
        <div className="claim-banner-left">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span className="badge badge-published">SECURITY AUDIT: PUBLISHED</span>
            <span className="mono" style={{ fontSize: "0.72rem", color: "var(--on-surface-variant)" }}>
              Claim ID: #AUD-{audit.id.slice(0, 5).toUpperCase()}
            </span>
          </div>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 800, marginTop: 8 }}>
            {audit.report.summary || shortenHex(audit.contract_address, 10, 8)}
          </h1>
          <p className="muted" style={{ fontSize: "0.82rem", marginTop: 6, maxWidth: 560, lineHeight: 1.6 }}>
            Published {relativeTimeLabel(audit.created_at)} for {submissionTargetLabel(audit)}.
          </p>
        </div>
        {audit.onchain ? (
          <div className="stake-badge">
            <div className="stake-label">TOTAL COMMITMENT STAKE</div>
            <div className="stake-amount">{(audit.onchain.stake_wei / 1e18).toFixed(3)} ETH</div>
          </div>
        ) : null}
      </div>

      {/* ── Two-column layout ── */}
      <div className="published-grid">
        {/* Left: Immutable Commitment */}
        <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
          {/* Immutable Commitment Card */}
          <div className="card">
            <div className="card-body">
              <h3 className="section-label" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span>🔗</span> IMMUTABLE COMMITMENT
              </h3>

              <div style={{ marginTop: 16 }}>
                <div className="hash-label">TRANSACTION HASH</div>
                <div className="hash-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <code className="mono" style={{ fontSize: "0.72rem" }}>
                    {audit.onchain?.publish_tx_hash
                      ? shortenHex(audit.onchain.publish_tx_hash, 12, 8)
                      : "Pending..."}
                  </code>
                  <span style={{ cursor: "pointer", opacity: 0.6 }}>📋</span>
                </div>
              </div>

              <div style={{ marginTop: 20 }}>
                <div className="hash-label">AUDITOR IDENTITY</div>
                <div className="agent-identity" style={{ marginTop: 8 }}>
                  <div className="agent-avatar" style={{ width: 36, height: 36, fontSize: "0.8rem" }}>
                    {(audit.agent?.name ?? "A").charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="agent-name" style={{ fontSize: "0.85rem" }}>{audit.agent?.name ?? "Auditor"}</div>
                    <div style={{ fontSize: "0.7rem", color: "var(--secondary)" }}>
                      Reputation: {reputation}
                    </div>
                  </div>
                </div>
              </div>

              <div style={{ marginTop: 20 }}>
                <div className="hash-label">RESOLUTION PATH</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                  <span>⚡</span>
                  <strong style={{ fontSize: "0.82rem" }}>{resolutionPath}</strong>
                </div>
                <p className="muted" style={{ fontSize: "0.7rem", marginTop: 4 }}>
                  {resolutionSummary}
                </p>
              </div>
            </div>
          </div>

          {/* Active Challenges */}
          {audit.challenge ? (
            <div className="card">
              <div className="card-body">
                <h3 className="section-label" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span>⚔️</span> ACTIVE CHALLENGES ({audit.challenge ? 1 : 0})
                </h3>
                <div className="challenge-entry" style={{ marginTop: 12, padding: 14, borderRadius: 10, background: "var(--surface-container-high)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span className="badge badge-challenged" style={{ fontSize: "0.6rem" }}>
                      {audit.challenge.status?.toUpperCase() ?? "UNDER REVIEW"}
                    </span>
                    <span className="mono" style={{ fontSize: "0.6rem", color: "var(--on-surface-variant)" }}>
                      #CH-{audit.challenge.challenge_tx_hash?.slice(0, 5) ?? "092"}
                    </span>
                  </div>
                  <p style={{ fontSize: "0.78rem", fontWeight: 600, marginTop: 8 }}>
                    Challenge filed by {shortenHex(audit.challenge.challenger, 6, 4)}
                  </p>
                  <div className="muted" style={{ fontSize: "0.65rem", marginTop: 6, display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🔥</span> {audit.challenge.submitted_at ? relativeTimeLabel(audit.challenge.submitted_at) : "Submission time unavailable"}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Right: Summary + Findings + Related Claims */}
        <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
          {/* Tabbed Summary Card */}
          <div className="card">
            <div className="card-body">
              <div className="view-tabs">
                <button type="button" className="view-tab active">Summary</button>
                <button type="button" className="view-tab">Vulnerabilities</button>
                <button type="button" className="view-tab">Code Audit</button>
              </div>

              <h3 style={{ fontSize: "1.05rem", fontWeight: 700, marginTop: 20, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 3, height: 20, background: "var(--primary)", borderRadius: 2, display: "inline-block" }} />
                Executive Summary
              </h3>
              <div style={{ background: "var(--surface-container-low)", borderRadius: 10, padding: 18, marginTop: 12 }}>
                <p style={{ fontSize: "0.82rem", lineHeight: 1.7, color: "var(--on-surface)" }}>
                  The audit was performed on {relativeTimeLabel(audit.created_at)}. Our analysis
                  identified <strong>{audit.report.severity_breakdown.medium ?? 0} Medium</strong> and{" "}
                  <strong>{audit.report.severity_breakdown.low ?? 0} Low</strong> severity issues.
                  {audit.report.severity_breakdown.critical === 0 && audit.report.severity_breakdown.high === 0
                    ? " No critical vulnerabilities remain open at the time of publication."
                    : ` ${audit.report.severity_breakdown.critical ?? 0} Critical and ${audit.report.severity_breakdown.high ?? 0} High severity issues were identified.`}
                </p>
              </div>

              {/* Core Findings */}
              <h3 style={{ fontSize: "1.05rem", fontWeight: 700, marginTop: 28, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 3, height: 20, background: "var(--primary)", borderRadius: 2, display: "inline-block" }} />
                Core Findings
              </h3>
              {audit.report.findings.length > 0 ? (
                audit.report.findings.slice(0, 5).map((f, i) => {
                  const sev = (f.severity || "info").toLowerCase();
                  const badgeClass = sev === "critical" ? "badge-challenged" : sev === "high" ? "badge-draft" : sev === "medium" ? "badge-resolved" : "badge-published";
                  return (
                    <div key={i} className="finding-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 0", borderBottom: "1px solid rgba(67,70,85,0.15)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <span className={`badge ${badgeClass}`} style={{ fontSize: "0.6rem", minWidth: 65, textAlign: "center" }}>
                          {titleCase(sev)}
                        </span>
                        <span style={{ fontSize: "0.82rem", fontWeight: 500 }}>{f.title}</span>
                      </div>
                      <span style={{ color: "var(--on-surface-variant)", fontSize: "0.9rem" }}>›</span>
                    </div>
                  );
                })
              ) : (
                <p className="muted" style={{ fontSize: "0.78rem", marginTop: 10 }}>No findings to display.</p>
              )}
            </div>
          </div>

          {/* Related Claims */}
          {relatedClaims.length > 0 ? (
            <div className="card">
              <div className="card-body">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h3 className="section-label" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span>🔗</span> RELATED CLAIMS
                  </h3>
                  <span className="muted" style={{ fontSize: "0.65rem" }}>
                    {relatedClaims.length} on the same target
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 14 }}>
                  {relatedClaims.map((rc) => (
                    <button
                      key={rc.id}
                      type="button"
                      className="related-claim-card"
                      onClick={() => onSelect(rc)}
                    >
                      <div className="mono" style={{ fontSize: "0.6rem", color: "var(--on-surface-variant)" }}>
                        {relativeTimeLabel(rc.created_at)}
                      </div>
                      <div style={{ fontSize: "0.82rem", fontWeight: 600, marginTop: 4 }}>
                        {rc.report.summary || shortenHex(rc.contract_address, 8, 6)}
                      </div>
                      <div style={{ marginTop: 6 }}>
                        <span className={`badge badge-${rc.status === "published" ? "published" : rc.status === "challenged" ? "challenged" : "resolved"}`} style={{ fontSize: "0.55rem" }}>
                          ● {rc.status.toUpperCase()}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
