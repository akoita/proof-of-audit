"use client";

import type { AuditRecord } from "../lib/types";
import {
  relativeTimeLabel,
  shortenHex,
  statusTone,
  titleCase,
} from "../lib/format";

type AuditCardProps = {
  audit: AuditRecord;
};

function securityScore(confidence: string): number {
  switch (confidence) {
    case "high": return 94;
    case "medium": return 72;
    case "low": return 45;
    default: return 60;
  }
}

const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;

export function AuditCard({ audit }: AuditCardProps) {
  const score = securityScore(audit.report.confidence);
  const statusClass = `badge-${audit.status === "draft" ? "draft" : audit.status === "published" ? "published" : audit.status === "challenged" ? "challenged" : "resolved"}`;

  return (
    <div className="card">
      {/* Card header: badge + title + date + security score */}
      <div className="card-header">
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span className={`badge ${statusClass}`} data-testid="current-audit-status">
            {audit.status}
          </span>
          <div>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 700, margin: 0 }}>
              {audit.report.summary || audit.contract_address}
            </h2>
            <p className="mono" style={{ fontSize: "0.72rem", color: "var(--on-surface-variant)", marginTop: 4 }}>
              Generated: {relativeTimeLabel(audit.created_at)}
            </p>
          </div>
        </div>
        <div className="security-score">
          <div>
            <span className="score-value">{score}</span>
            <span className="score-suffix">/100</span>
          </div>
          <div className="score-label">Security Score</div>
        </div>
      </div>

      {/* Severity grid: 4 columns */}
      <div className="severity-grid">
        {SEVERITY_ORDER.map((sev) => (
          <div key={sev} className="severity-cell" data-severity={sev}>
            <div className="severity-type">{titleCase(sev)}</div>
            <div className="severity-count">
              {audit.report.severity_breakdown[sev] ?? 0}
            </div>
          </div>
        ))}
      </div>

      {/* Findings */}
      <div className="card-body">
        <h3 className="section-label" style={{ letterSpacing: "0.15em" }}>
          Detailed Analysis Findings
        </h3>
        {audit.report.findings && audit.report.findings.length > 0 ? (
          audit.report.findings.map((f, i) => {
            const sev = (f.severity || "info").toLowerCase();
            const sevClass = `badge-${sev === "critical" ? "challenged" : sev === "high" ? "draft" : sev === "medium" ? "resolved" : "published"}`;
            return (
              <div key={i} className="finding-item" data-severity={sev}>
                <div className="finding-header">
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className={`badge ${sevClass}`}>
                      {titleCase(sev)} Risk
                    </span>
                    <h4>{f.title}</h4>
                  </div>
                  {f.category ? (
                    <span className="finding-category">{f.category}</span>
                  ) : null}
                </div>
                <p className="finding-desc">{f.description}</p>
              </div>
            );
          })
        ) : (
          <div className="finding-item" data-severity="info">
            <div className="finding-header">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="badge badge-published">Info</span>
                <h4>No benchmark issue found across the supported checks.</h4>
              </div>
            </div>
            <p className="finding-desc">
              The auditor did not match a benchmark issue across the supported checks.
            </p>
          </div>
        )}

        {/* Evidence Hashes */}
        <div style={{ marginTop: 32, paddingTop: 24, borderTop: "1px solid rgba(67,70,85,0.2)" }}>
          <h3 className="section-label" style={{ letterSpacing: "0.15em" }}>
            Evidence Verification Hashes
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div className="hash-card">
              <div className="hash-label">Report Hash</div>
              <code className="mono">{shortenHex(audit.report.report_hash, 8, 6)}</code>
            </div>
            <div className="hash-card">
              <div className="hash-label">Metadata Hash</div>
              <code className="mono">{shortenHex(audit.report.metadata_hash, 8, 6)}</code>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
