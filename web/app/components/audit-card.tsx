"use client";

import type { AuditRecord } from "../lib/types";
import {
  lifecycleLabel,
  relativeTimeLabel,
  shortenHex,
  statusTone,
  submissionModeLabel,
  submissionTargetLabel,
  titleCase,
} from "../lib/format";

type AuditCardProps = {
  audit: AuditRecord;
};

function confidencePercent(confidence: string): number {
  switch (confidence) {
    case "high": return 85;
    case "medium": return 60;
    case "low": return 35;
    default: return 50;
  }
}

export function AuditCard({ audit }: AuditCardProps) {
  const severityOrder = ["critical", "high", "medium", "low", "info"];
  const pct = confidencePercent(audit.report.confidence);

  return (
    <div className="audit-card-inner">
      {/* Card header — title + status */}
      <div className="audit-card-header">
        <h2>{audit.report.summary}</h2>
        <span
          className="audit-status-badge"
          data-testid="current-audit-status"
          data-tone={statusTone(audit.status)}
        >
          {audit.status}
        </span>
      </div>

      {/* Report summary: gauge + severity side by side */}
      <div className="report-summary-row">
        <div className="report-summary-label">Report summary</div>

        <div className="report-summary-content">
          {/* Gauge */}
          <div className="confidence-gauge">
            <svg viewBox="0 0 100 100" className="gauge-ring">
              <circle cx="50" cy="50" r="40" fill="none" stroke="var(--line)" strokeWidth="8" />
              <circle
                cx="50" cy="50" r="40" fill="none"
                stroke="var(--accent)"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${pct * 2.512} 251.2`}
                transform="rotate(-90 50 50)"
                className="gauge-fill"
              />
            </svg>
            <div className="gauge-label">
              <strong>{pct}%</strong>
            </div>
          </div>

          {/* Severity bars */}
          <div className="severity-section">
            <div className="severity-section-title">Severity</div>
            {severityOrder.map((sev) => {
              const count = audit.report.severity_breakdown[sev] ?? 0;
              if (sev === "info" && count === 0) return null;
              return (
                <div key={sev} className="severity-row">
                  <span className="severity-count-left">{count}</span>
                  <span className="severity-label">{titleCase(sev)}</span>
                  <div className="severity-bar-track">
                    <div
                      className="severity-bar-fill"
                      data-severity={sev}
                      style={{ width: `${Math.min(count * 25, 100)}%` }}
                    />
                  </div>
                  <span className="severity-count">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Meta chips */}
      <div className="audit-summary-bar">
        <span>{audit.agent.id}</span>
        <span>{submissionModeLabel(audit.submission.input_kind)}</span>
        <span>{audit.report.benchmark_id}</span>
        <span>{audit.report.confidence} confidence</span>
        <span title={audit.contract_address}>{submissionTargetLabel(audit)}</span>
      </div>

      <p className="muted audit-actor-note">
        {audit.agent.name} is the named actor responsible for this claim.
      </p>

      {/* Compact stats row */}
      <div className="metrics-grid">
        <div>
          <span>Auditor</span>
          <strong>{audit.agent.name}</strong>
        </div>
        <div>
          <span>Status</span>
          <strong>{lifecycleLabel(audit)}</strong>
        </div>
        <div>
          <span>Created</span>
          <strong>{relativeTimeLabel(audit.created_at)}</strong>
        </div>
        <div>
          <span>Findings</span>
          <strong>{audit.report.finding_count}</strong>
        </div>
        <div>
          <span>Max severity</span>
          <strong>{audit.report.max_severity}</strong>
        </div>
        <div>
          <span>Report hash</span>
          <strong title={audit.report.report_hash}>
            {shortenHex(audit.report.report_hash, 10, 6)}
          </strong>
        </div>
      </div>
    </div>
  );
}
