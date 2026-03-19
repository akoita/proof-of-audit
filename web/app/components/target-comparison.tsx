"use client";

import type { AuditRecord, TargetComparisonResponse } from "../lib/types";
import {
  formatEth,
  lifecycleLabel,
  reputationLabel,
  severityRankLabel,
  statusTone,
  submissionModeLabel,
  titleCase,
} from "../lib/format";

type TargetComparisonProps = {
  audit: AuditRecord | null;
  comparison: TargetComparisonResponse | null;
  isLoaded: boolean;
  onSelect: (audit: AuditRecord) => void;
};

export function TargetComparison({ audit, comparison, isLoaded, onSelect }: TargetComparisonProps) {
  const items = comparison?.items ?? [];
  const summary = comparison?.summary;

  return (
    <div className="card">
      <div className="card-body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "1.1rem" }}>🔍</span>
            Target Comparison
          </h3>
          <span style={{
            background: "var(--surface-container-high)",
            borderRadius: 20,
            padding: "3px 10px",
            fontSize: "0.65rem",
            fontWeight: 600,
          }}>
            {summary?.claim_count ?? (isLoaded ? 0 : "…")} claims
          </span>
        </div>

        {!audit ? (
          <div className="empty-panel" style={{ padding: "24px 0" }}>
            <p className="muted" style={{ fontSize: "0.78rem" }}>Create or select a claim to compare.</p>
          </div>
        ) : !isLoaded ? (
          <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>Loading comparison for this target…</p>
        ) : items.length === 0 ? (
          <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>No other claims for this target yet.</p>
        ) : (
          <>
            {/* Summary stats */}
            {summary ? (
              <div style={{ display: "flex", gap: 16, marginTop: 14, flexWrap: "wrap" }}>
                <span style={{ fontSize: "0.65rem", color: "var(--secondary)" }}>
                  ● {summary.published_count} published
                </span>
                <span style={{ fontSize: "0.65rem", color: "var(--tertiary)" }}>
                  ● {summary.challenged_count} challenged
                </span>
                <span style={{ fontSize: "0.65rem", color: "var(--primary)" }}>
                  ● {summary.resolved_count} resolved
                </span>
                <span className="muted" style={{ fontSize: "0.65rem" }}>
                  max {severityRankLabel(summary.max_severity)}
                </span>
              </div>
            ) : null}

            {/* Comparison grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 16 }}>
              {items.map((item) => {
                const isActive = item.id === audit?.id;
                const tone = statusTone(item.status);
                const badgeClass = item.status === "published" ? "badge-published"
                  : item.status === "challenged" ? "badge-challenged"
                  : item.status === "resolved" ? "badge-published"
                  : "badge-draft";

                return (
                  <button
                    key={item.id}
                    type="button"
                    className="related-claim-card"
                    onClick={() => onSelect(item)}
                    style={{
                      borderLeft: isActive ? "3px solid var(--primary)" : "3px solid transparent",
                      opacity: isActive ? 1 : 0.85,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontWeight: 600, fontSize: "0.78rem" }}>{item.agent.name}</span>
                      <span className={`badge ${badgeClass}`} style={{ fontSize: "0.5rem" }}>
                        {item.status.toUpperCase()}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.65rem", color: "var(--on-surface-variant)", marginBottom: 4 }}>
                      {submissionModeLabel(item.submission.input_kind)}
                    </div>
                    <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--on-surface)", marginBottom: 4 }}>
                      {lifecycleLabel(item)}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", marginTop: 4 }}>
                      <span>
                        {item.onchain
                          ? <span style={{ color: "var(--secondary)" }}>stake {formatEth(item.onchain.stake_wei)}</span>
                          : <span className="muted">not published</span>}
                      </span>
                      <span className="muted">
                        {item.report.finding_count} finding{item.report.finding_count !== 1 ? "s" : ""}
                      </span>
                    </div>
                    <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>
                      rep {reputationLabel(item.agent.reputation)} · sev {severityRankLabel(item.report.max_severity)}
                    </div>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
