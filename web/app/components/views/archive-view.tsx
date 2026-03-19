"use client";

import type { AuditRecord } from "../../lib/types";
import { shortenHex, titleCase, relativeTimeLabel } from "../../lib/format";

type ArchiveViewProps = {
  audits: AuditRecord[];
  onSelect: (a: AuditRecord) => void;
};

export function ArchiveView({ audits, onSelect }: ArchiveViewProps) {
  const resolved = audits.filter((a) => a.status === "resolved" || a.status === "published");

  return (
    <div className="view-archive">
      <div className="card">
        <div className="card-body">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 700 }}>Audit History Archive</h2>
            <span className="muted" style={{ fontSize: "0.72rem" }}>
              {resolved.length} record{resolved.length !== 1 ? "s" : ""}
            </span>
          </div>

          {resolved.length === 0 ? (
            <div className="empty-panel" style={{ marginTop: 24 }}>
              <strong>No archived audits</strong>
              <p className="muted">Completed and resolved claims will appear here after the challenge window closes.</p>
            </div>
          ) : (
            <div className="archive-list" style={{ marginTop: 16 }}>
              {resolved.map((a) => {
                const maxSev = a.report.max_severity;
                const sevLabel = maxSev >= 4 ? "CRITICAL" : maxSev >= 3 ? "HIGH" : maxSev >= 2 ? "MEDIUM" : "LOW";
                const sevClass = maxSev >= 4 ? "badge-challenged" : maxSev >= 3 ? "badge-draft" : maxSev >= 2 ? "badge-resolved" : "badge-published";
                return (
                  <button
                    key={a.id}
                    type="button"
                    className="archive-row"
                    onClick={() => onSelect(a)}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 2 }}>
                      <span style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--secondary)", flexShrink: 0 }} />
                      <div>
                        <div style={{ fontWeight: 600, fontSize: "0.85rem" }}>
                          {a.report.summary || shortenHex(a.contract_address, 10, 8)}
                        </div>
                        <div className="mono" style={{ fontSize: "0.6rem", color: "var(--on-surface-variant)" }}>
                          {shortenHex(a.contract_address, 8, 6)} · {a.report.finding_count} findings
                        </div>
                      </div>
                    </div>
                    <div style={{ flex: 1, textAlign: "center" }}>
                      <span className={`badge ${sevClass}`} style={{ fontSize: "0.55rem" }}>{sevLabel}</span>
                    </div>
                    <div style={{ flex: 1, textAlign: "center" }}>
                      <span className="badge badge-published" style={{ fontSize: "0.55rem" }}>
                        ● {titleCase(a.status)}
                      </span>
                    </div>
                    <div className="muted" style={{ flex: 1, textAlign: "right", fontSize: "0.7rem" }}>
                      {relativeTimeLabel(a.created_at)}
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {resolved.length > 0 ? (
            <div style={{ textAlign: "center", marginTop: 20 }}>
              <span className="muted" style={{ fontSize: "0.72rem", letterSpacing: 1.5 }}>
                VIEW AUDIT HISTORY ARCHIVE ({resolved.length} MORE)
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
