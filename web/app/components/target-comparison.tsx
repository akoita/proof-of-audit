"use client";

import { useState } from "react";
import type { AuditRecord, TargetComparisonResponse } from "../lib/types";
import {
  confidenceLabel,
  formatEth,
  lifecycleLabel,
  reputationLabel,
  severityRankLabel,
  submissionModeLabel,
} from "../lib/format";

type TargetComparisonProps = {
  audit: AuditRecord | null;
  comparison: TargetComparisonResponse | null;
  isLoaded: boolean;
  onSelect: (audit: AuditRecord) => void;
  title?: string;
  description?: string;
  emptyMessage?: string;
  challengeWindowSeconds?: number | null;
};

const PAGE_SIZE = 6;

function dominantValue<T>(values: T[]): T | null {
  if (values.length === 0) return null;
  const counts = new Map<T, number>();
  let selected = values[0];
  let maxCount = 0;
  for (const value of values) {
    const nextCount = (counts.get(value) ?? 0) + 1;
    counts.set(value, nextCount);
    if (nextCount > maxCount) {
      maxCount = nextCount;
      selected = value;
    }
  }
  return selected;
}

function findingFingerprint(audit: AuditRecord): string {
  return audit.report.findings
    .map((finding) => `${finding.severity}:${finding.title}`)
    .sort()
    .join("|");
}

export function TargetComparison({
  audit,
  comparison,
  isLoaded,
  onSelect,
  title = "Target Comparison",
  description,
  emptyMessage = "No other claims for this target yet.",
  challengeWindowSeconds,
}: TargetComparisonProps) {
  const [expanded, setExpanded] = useState(false);
  const items = comparison?.items ?? [];
  const summary = comparison?.summary;
  const visible = expanded ? items : items.slice(0, PAGE_SIZE);
  const hasMore = items.length > PAGE_SIZE;
  const activeId = audit?.id ?? null;
  const consensusSeverity = dominantValue(items.map((item) => item.report.max_severity));
  const consensusFindingCount = dominantValue(items.map((item) => item.report.finding_count));
  const consensusConfidence = dominantValue(items.map((item) => item.report.confidence));
  const consensusFingerprint = dominantValue(items.map(findingFingerprint));
  const disagreementSignals = [
    new Set(items.map((item) => item.report.max_severity)).size > 1 ? "Severity varies across claims" : null,
    new Set(items.map((item) => item.report.finding_count)).size > 1 ? "Finding volume differs" : null,
    new Set(items.map((item) => item.report.confidence)).size > 1 ? "Confidence differs" : null,
    new Set(items.map(findingFingerprint)).size > 1 ? "Finding summaries disagree" : null,
  ].filter((value): value is string => Boolean(value));
  const publishedWindows = items
    .map((item) => {
      const publishedAt = item.onchain?.published_at ? new Date(item.onchain.published_at) : null;
      if (!publishedAt || Number.isNaN(publishedAt.getTime()) || !challengeWindowSeconds) {
        return null;
      }
      return publishedAt.getTime() + (challengeWindowSeconds * 1000);
    })
    .filter((value): value is number => value != null);
  const responseWindowState =
    publishedWindows.length === 0
      ? null
      : Math.max(...publishedWindows) > Date.now()
        ? "Response window still open"
        : "Response window closed";

  return (
    <div className="card">
      <div className="card-body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "1.1rem" }}>🔍</span>
            {title}
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

        {description ? (
          <p className="muted" style={{ fontSize: "0.76rem", marginTop: 10, lineHeight: 1.6 }}>
            {description}
          </p>
        ) : null}

        {responseWindowState ? (
          <div className="marketplace-chip-row" style={{ marginTop: 12 }}>
            <span className="pill">{responseWindowState}</span>
            {disagreementSignals.length > 0 ? (
              <span className="pill">{disagreementSignals.length} disagreement signal{disagreementSignals.length !== 1 ? "s" : ""}</span>
            ) : null}
          </div>
        ) : null}

        {!isLoaded ? (
          <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>Loading comparison for this target…</p>
        ) : items.length === 0 ? (
          <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>{emptyMessage}</p>
        ) : (
          <>
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

            {disagreementSignals.length > 0 ? (
              <div className="marketplace-chip-row" style={{ marginTop: 14 }}>
                {disagreementSignals.map((signal) => (
                  <span key={signal} className="pill">{signal}</span>
                ))}
              </div>
            ) : null}

            <div className="comparison-grid" style={{ marginTop: 16 }}>
              {visible.map((item) => {
                const isActive = item.id === activeId;
                const badgeClass = item.status === "published" ? "badge-published"
                  : item.status === "challenged" ? "badge-challenged"
                  : item.status === "resolved" ? "badge-published"
                  : "badge-draft";
                const disagreementBadges = [
                  item.report.max_severity !== consensusSeverity ? "Severity" : null,
                  item.report.finding_count !== consensusFindingCount ? "Finding count" : null,
                  item.report.confidence !== consensusConfidence ? "Confidence" : null,
                  findingFingerprint(item) !== consensusFingerprint ? "Finding set" : null,
                ].filter((value): value is string => Boolean(value));
                const severityBreakdownEntries = Object.entries(item.report.severity_breakdown)
                  .filter(([, count]) => count > 0)
                  .sort((left, right) => right[1] - left[1]);

                return (
                  <button
                    key={item.id}
                    type="button"
                    className="related-claim-card"
                    onClick={() => onSelect(item)}
                    style={{
                      borderLeft: isActive ? "3px solid var(--primary)" : "3px solid transparent",
                      opacity: isActive ? 1 : 0.85,
                      display: "grid",
                      gap: 10,
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
                    <div className="marketplace-chip-row">
                      <span className="pill">
                        {item.onchain
                          ? `Stake ${formatEth(item.onchain.stake_wei)}`
                          : "Not yet published"}
                      </span>
                      <span className="pill">
                        {severityRankLabel(item.report.max_severity)} severity
                      </span>
                      <span className="pill">
                        {confidenceLabel(item.report.confidence)}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", marginTop: 4 }}>
                      <span className="muted">
                        {item.report.finding_count} finding{item.report.finding_count !== 1 ? "s" : ""}
                      </span>
                      <span className="muted">
                        {reputationLabel(item.agent.reputation)}
                      </span>
                    </div>
                    <div className="marketplace-chip-row">
                      {severityBreakdownEntries.length > 0 ? severityBreakdownEntries.map(([severity, count]) => (
                        <span key={severity} className="pill">
                          {severity} {count}
                        </span>
                      )) : (
                        <span className="pill">No findings</span>
                      )}
                    </div>
                    {item.report.findings.length > 0 ? (
                      <div className="muted" style={{ fontSize: "0.7rem", lineHeight: 1.6 }}>
                        Top findings: {item.report.findings.slice(0, 3).map((finding) => finding.title).join(" · ")}
                      </div>
                    ) : null}
                    <div className="marketplace-chip-row">
                      {disagreementBadges.length > 0 ? disagreementBadges.map((badge) => (
                        <span key={badge} className="pill">{badge} differs</span>
                      )) : (
                        <span className="pill">Aligned with comparison consensus</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>

            {hasMore ? (
              <button
                type="button"
                className="btn-outline"
                onClick={() => setExpanded(!expanded)}
                style={{ width: "100%", marginTop: 14, justifyContent: "center", fontSize: "0.72rem" }}
              >
                {expanded ? "Show Less" : `Show ${items.length - PAGE_SIZE} More Claims`}
              </button>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
