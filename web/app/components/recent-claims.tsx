"use client";

import type { AuditRecord } from "../lib/types";
import {
  lifecycleLabel,
  statusTone,
  submissionTargetLabel,
} from "../lib/format";

type RecentClaimsProps = {
  audits: AuditRecord[];
  activeId: string | null;
  isLoaded: boolean;
  onSelect: (audit: AuditRecord) => void;
};

export function RecentClaims({ audits, activeId, isLoaded, onSelect }: RecentClaimsProps) {
  return (
    <div>
      <div className="section-heading">
        <p>Recent claims</p>
        <span className="count-badge">{audits.length}</span>
      </div>
      <div className="recent-list">
        {!isLoaded ? (
          <p className="muted">Loading recent audits.</p>
        ) : audits.length === 0 ? (
          <p className="muted">No audits yet.</p>
        ) : (
          audits.map((audit) => (
            <button
              key={audit.id}
              type="button"
              className="recent-item"
              data-selected={audit.id === activeId}
              onClick={() => onSelect(audit)}
            >
              <div className="card-header">
                <p>{audit.report.benchmark_id}</p>
                <span data-tone={statusTone(audit.status)}>{audit.status}</span>
              </div>
              <small>{audit.agent.name}</small>
              <strong title={audit.contract_address}>{submissionTargetLabel(audit)}</strong>
              <p>{audit.report.summary}</p>
              <small>{lifecycleLabel(audit)}</small>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
