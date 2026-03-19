"use client";

import type { AuditRecord, TargetComparisonResponse } from "../lib/types";
import {
  formatEth,
  lifecycleLabel,
  reputationLabel,
  severityRankLabel,
  statusTone,
  submissionModeLabel,
} from "../lib/format";

type TargetComparisonProps = {
  audit: AuditRecord | null;
  comparison: TargetComparisonResponse | null;
  isLoaded: boolean;
  onSelect: (audit: AuditRecord) => void;
};

export function TargetComparison({ audit, comparison, isLoaded, onSelect }: TargetComparisonProps) {
  return (
    <div className="comparison-block">
      <div className="section-heading">
        <p>Target comparison</p>
        <span className="count-badge">
          {comparison?.summary.claim_count ?? (isLoaded ? 0 : "…")}
        </span>
      </div>
      {!audit ? (
        <p className="muted">Create or select a claim to compare.</p>
      ) : !isLoaded ? (
        <p className="muted">Loading comparison for this target.</p>
      ) : !comparison || comparison.items.length === 0 ? (
        <p className="muted">No other claims for this target yet.</p>
      ) : (
        <>
          <p className="muted comparison-summary">
            {comparison.summary.published_count} published ·{" "}
            {comparison.summary.challenged_count} challenged ·{" "}
            {comparison.summary.resolved_count} resolved · max{" "}
            {severityRankLabel(comparison.summary.max_severity)}
          </p>
          <div className="comparison-list">
            {comparison.items.map((item) => (
              <button
                key={item.id}
                type="button"
                className="comparison-item"
                data-selected={item.id === audit?.id}
                onClick={() => onSelect(item)}
              >
                <div className="card-header">
                  <p>{item.agent.name}</p>
                  <span data-tone={statusTone(item.status)}>{item.status}</span>
                </div>
                <small>{submissionModeLabel(item.submission.input_kind)}</small>
                <strong>{lifecycleLabel(item)}</strong>
                <p>
                  {item.onchain
                    ? `stake ${formatEth(item.onchain.stake_wei)}`
                    : "not yet published"}
                </p>
                <p>
                  reputation {reputationLabel(item.agent.reputation)} ·{" "}
                  {item.agent.reputation?.resolved_challenge_count ?? 0} resolved
                </p>
                <small>
                  severity {severityRankLabel(item.report.max_severity)} ·{" "}
                  {item.report.finding_count} finding{item.report.finding_count === 1 ? "" : "s"}
                </small>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
