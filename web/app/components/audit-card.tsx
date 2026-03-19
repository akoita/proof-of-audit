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

export function AuditCard({ audit }: AuditCardProps) {
  const severityEntries = Object.entries(audit.report.severity_breakdown).filter(
    ([, count]) => count > 0,
  );

  return (
    <div className="audit-card-inner">
      {/* Header row */}
      <div className="section-heading">
        <p>Current audit</p>
        <span
          data-testid="current-audit-status"
          data-tone={statusTone(audit.status)}
        >
          {audit.status}
        </span>
      </div>

      {/* Summary chips */}
      <div className="audit-summary-bar">
        <span>{audit.agent.id}</span>
        <span>{submissionModeLabel(audit.submission.input_kind)}</span>
        <span>{audit.report.benchmark_id}</span>
        <span>{audit.report.confidence} confidence</span>
        <span title={audit.contract_address}>{submissionTargetLabel(audit)}</span>
      </div>

      {/* Headline */}
      <h2>{audit.report.summary}</h2>
      <p className="muted">
        {audit.agent.name} is the named actor responsible for this claim.
      </p>

      {/* Stats + gauge row */}
      <div className="audit-metrics">
        {/* Confidence gauge */}
        <div className="confidence-gauge">
          <svg viewBox="0 0 80 80" className="gauge-ring">
            <circle
              cx="40"
              cy="40"
              r="34"
              fill="none"
              stroke="var(--line)"
              strokeWidth="6"
            />
            <circle
              cx="40"
              cy="40"
              r="34"
              fill="none"
              stroke="var(--accent)"
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={`${(audit.report.confidence === "high" ? 85 : audit.report.confidence === "medium" ? 60 : 35) * 2.136} 214`}
              transform="rotate(-90 40 40)"
              className="gauge-fill"
            />
          </svg>
          <div className="gauge-label">
            <strong>{titleCase(audit.report.confidence)}</strong>
            <span>Confidence</span>
          </div>
        </div>

        {/* Key metrics */}
        <div className="metrics-grid">
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

      {/* Severity bars */}
      {severityEntries.length > 0 && (
        <div className="severity-bars">
          {severityEntries.map(([severity, count]) => (
            <div key={severity} className="severity-row">
              <span className="severity-label">{titleCase(severity)}</span>
              <div className="severity-bar-track">
                <div
                  className="severity-bar-fill"
                  data-severity={severity}
                  style={{ width: `${Math.min(count * 25, 100)}%` }}
                />
              </div>
              <span className="severity-count">{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
