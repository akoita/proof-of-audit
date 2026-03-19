"use client";

import type { AuditRecord } from "../lib/types";
import {
  lifecycleLabel,
  statusTone,
  submissionTargetLabel,
  titleCase,
  shortenHex,
  severityRankLabel,
} from "../lib/format";

type RecentClaimsProps = {
  audits: AuditRecord[];
  activeId: string | null;
  isLoaded: boolean;
  onSelect: (audit: AuditRecord) => void;
};

export function RecentClaims({ audits, activeId, isLoaded, onSelect }: RecentClaimsProps) {
  return (
    <div className="card">
      <div className="card-body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "1.1rem" }}>📋</span>
            Recent Forensic Claims
          </h3>
          <span style={{
            background: "var(--surface-container-high)",
            borderRadius: 20,
            padding: "3px 10px",
            fontSize: "0.65rem",
            fontWeight: 600,
          }}>
            {audits.length} claims
          </span>
        </div>

        {!isLoaded ? (
          <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>Loading recent audits…</p>
        ) : audits.length === 0 ? (
          <div className="empty-panel" style={{ padding: "24px 0" }}>
            <strong>No audits yet</strong>
            <p className="muted" style={{ fontSize: "0.78rem" }}>Submit a contract to generate your first claim.</p>
          </div>
        ) : (
          <div style={{ marginTop: 14 }}>
            {audits.map((audit) => {
              const isActive = audit.id === activeId;
              const badgeClass = audit.status === "published" ? "badge-published"
                : audit.status === "challenged" ? "badge-challenged"
                : audit.status === "resolved" ? "badge-published"
                : "badge-draft";
              const maxSev = audit.report.max_severity;
              const sevLabel = severityRankLabel(maxSev);

              return (
                <button
                  key={audit.id}
                  type="button"
                  className="forensic-row"
                  onClick={() => onSelect(audit)}
                  style={{
                    width: "100%",
                    background: isActive ? "var(--surface-container-low)" : "transparent",
                    border: "none",
                    cursor: "pointer",
                    textAlign: "left",
                    color: "var(--on-surface)",
                    borderLeft: isActive ? "3px solid var(--primary)" : "3px solid transparent",
                    paddingLeft: 12,
                    transition: "background 0.15s",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 2 }}>
                    <span style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: audit.status === "resolved" ? "var(--secondary)" : audit.status === "challenged" ? "var(--error)" : "var(--tertiary)",
                      flexShrink: 0,
                    }} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: "0.82rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {audit.report.summary || submissionTargetLabel(audit)}
                      </div>
                      <div className="mono" style={{ fontSize: "0.6rem", color: "var(--on-surface-variant)" }}>
                        {audit.agent.name} · {shortenHex(audit.contract_address, 6, 4)}
                      </div>
                    </div>
                  </div>
                  <div style={{ flex: 1, textAlign: "center" }}>
                    <span className={`badge ${badgeClass}`} style={{ fontSize: "0.5rem" }}>
                      {audit.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="muted" style={{ flex: 1, textAlign: "right", fontSize: "0.65rem", whiteSpace: "nowrap" }}>
                    {sevLabel} · {audit.report.finding_count} findings
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
