"use client";

import type { AuditRecord } from "../lib/types";
import { addressUrl, formatEth, isExplorerLink, shortenHex } from "../lib/format";

type OnchainCardProps = { audit: AuditRecord };

export function OnchainCard({ audit }: OnchainCardProps) {
  if (!audit.onchain) return null;
  const oc = audit.onchain;

  return (
    <div className="card">
      <div className="card-body">
        <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: "1.1rem" }}>🔗</span>
          On-Chain Commitment
          <span className="badge badge-published" style={{ marginLeft: "auto", fontSize: "0.55rem" }}>
            {oc.network.toUpperCase()}
          </span>
        </h3>

        <p className="muted" style={{ fontSize: "0.78rem", marginTop: 8, lineHeight: 1.6 }}>
          <strong>{oc.agent_name ?? audit.agent.name}</strong> staked{" "}
          <span style={{ color: "var(--secondary)", fontWeight: 700 }}>{formatEth(oc.stake_wei)}</span>{" "}
          behind this judgment.
        </p>

        {/* Key-value grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 16 }}>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">AUDIT ID</div>
            <div className="mono" style={{ fontSize: "0.82rem", fontWeight: 600, marginTop: 2 }}>
              {oc.audit_id ?? "pending"}
            </div>
          </div>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">CONTRACT</div>
            <div className="mono" style={{ fontSize: "0.72rem", marginTop: 2 }} title={oc.contract_address ?? ""}>
              {oc.contract_address ? shortenHex(oc.contract_address, 8, 6) : "—"}
            </div>
          </div>
        </div>

        <div className="hash-card" style={{ padding: "10px 14px", marginTop: 12 }}>
          <div className="hash-label">PUBLISH TX</div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
            <code className="mono" style={{ fontSize: "0.72rem" }} title={oc.publish_tx_hash}>
              {shortenHex(oc.publish_tx_hash, 12, 8)}
            </code>
            <span style={{ cursor: "pointer", opacity: 0.6, fontSize: "0.8rem" }}>📋</span>
          </div>
        </div>

        {/* Links */}
        <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
          {oc.publish_tx_url && isExplorerLink(oc.publish_tx_url) ? (
            <a href={oc.publish_tx_url} target="_blank" rel="noreferrer" className="btn-outline" style={{ fontSize: "0.7rem", padding: "6px 12px" }}>
              ↗ View Publish Tx
            </a>
          ) : (
            <span className="muted" style={{ fontSize: "0.65rem", display: "flex", alignItems: "center", gap: 4 }}>
              ✅ Confirmed locally
            </span>
          )}
          {addressUrl(oc.explorer_base_url, oc.contract_address ?? null) ? (
            <a
              href={addressUrl(oc.explorer_base_url, oc.contract_address ?? null) ?? undefined}
              target="_blank"
              rel="noreferrer"
              className="btn-outline"
              style={{ fontSize: "0.7rem", padding: "6px 12px" }}
            >
              ↗ View Registry
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}
