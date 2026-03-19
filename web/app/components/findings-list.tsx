"use client";

import type { Finding } from "../lib/types";
import { titleCase } from "../lib/format";

type FindingsListProps = { findings: Finding[] };

export function FindingsList({ findings }: FindingsListProps) {
  return (
    <div className="finding-list">
      <div className="section-heading findings-heading">
        <p>Findings</p>
        <span className="count-badge">{findings.length}</span>
      </div>
      {findings.length === 0 ? (
        <div className="finding-card">
          <strong>No benchmark issue found</strong>
          <p>
            The auditor did not match a benchmark issue across the supported checks.
          </p>
        </div>
      ) : (
        findings.map((finding) => (
          <div key={finding.finding_id} className="finding-card">
            <div className="card-header">
              <p>{finding.title}</p>
              <span data-severity={finding.severity}>{finding.severity}</span>
            </div>
            <p className="muted">
              {titleCase(finding.category)} · {titleCase(finding.confidence)} confidence
              {finding.affected_function ? ` · ${finding.affected_function}` : ""}
            </p>
            <p>{finding.description}</p>
            <p className="muted">{finding.impact}</p>
            <p className="muted">{finding.recommendation}</p>
            {finding.source_path ? (
              <p className="muted">
                Source: {finding.source_path}
                {finding.start_line ? `:${finding.start_line}` : ""}
                {finding.end_line && finding.end_line !== finding.start_line
                  ? `-${finding.end_line}`
                  : ""}
              </p>
            ) : null}
            {finding.evidence_uri ? (
              <p className="muted">Evidence: {finding.evidence_uri}</p>
            ) : null}
          </div>
        ))
      )}
    </div>
  );
}
