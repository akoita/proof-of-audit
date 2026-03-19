"use client";

import type { AuditRecord } from "../lib/types";
import {
  formatIdentitySource,
  isExplorerLink,
  shortenHex,
  statusTone,
} from "../lib/format";

type ValidationCardProps = { audit: AuditRecord };

export function ValidationCard({ audit }: ValidationCardProps) {
  if (!audit.validation) return null;
  const v = audit.validation;

  const statusColor = statusTone(v.status) === "confirmed" ? "var(--secondary)"
    : statusTone(v.status) === "warning" ? "var(--tertiary)"
    : "var(--on-surface-variant)";

  return (
    <div className="card">
      <div className="card-body">
        <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: "1.1rem" }}>🛡</span>
          Validation Bridge
          <span
            style={{ marginLeft: "auto", fontSize: "0.65rem", fontWeight: 600, color: statusColor, display: "flex", alignItems: "center", gap: 4 }}
          >
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: statusColor }} />
            {v.status.toUpperCase()}
          </span>
        </h3>

        <p className="muted" style={{ fontSize: "0.78rem", marginTop: 8, lineHeight: 1.6 }}>
          Mirrors this audit into <strong>{formatIdentitySource(v.source)}</strong> validation infrastructure.
        </p>

        {/* Stats row */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 16 }}>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">AGENT ID</div>
            <div className="mono" style={{ fontSize: "0.82rem", fontWeight: 600, marginTop: 2 }}>{v.agent_id}</div>
          </div>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">RESPONSE</div>
            <div style={{ fontSize: "0.82rem", fontWeight: 600, marginTop: 2, color: v.response !== null && v.response !== undefined ? "var(--secondary)" : "var(--on-surface-variant)" }}>
              {v.response === null || v.response === undefined ? "pending" : `${v.response}/100`}
            </div>
          </div>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">TAG</div>
            <div style={{ fontSize: "0.82rem", fontWeight: 600, marginTop: 2 }}>{v.response_tag ?? "pending"}</div>
          </div>
        </div>

        {/* Addresses */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">VALIDATOR</div>
            <div className="mono" style={{ fontSize: "0.7rem", marginTop: 2 }} title={v.validator_address}>
              {shortenHex(v.validator_address, 8, 6)}
            </div>
          </div>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">REGISTRY</div>
            <div className="mono" style={{ fontSize: "0.7rem", marginTop: 2 }} title={v.registry_address}>
              {shortenHex(v.registry_address, 8, 6)}
            </div>
          </div>
        </div>

        {/* Request hash */}
        <div className="hash-card" style={{ padding: "10px 14px", marginTop: 10 }}>
          <div className="hash-label">REQUEST HASH</div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
            <code className="mono" style={{ fontSize: "0.7rem" }} title={v.request_hash}>
              {shortenHex(v.request_hash, 12, 8)}
            </code>
            <span style={{ cursor: "pointer", opacity: 0.6, fontSize: "0.8rem" }}>📋</span>
          </div>
        </div>

        {/* Links */}
        <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
          <a href={v.request_uri} target="_blank" rel="noreferrer" className="btn-outline" style={{ fontSize: "0.7rem", padding: "6px 12px" }}>
            ↗ View Request
          </a>
          {v.response_uri ? (
            <a href={v.response_uri} target="_blank" rel="noreferrer" className="btn-outline" style={{ fontSize: "0.7rem", padding: "6px 12px" }}>
              ↗ View Response
            </a>
          ) : null}
          {v.request_tx_url && isExplorerLink(v.request_tx_url) ? (
            <a href={v.request_tx_url} target="_blank" rel="noreferrer" className="btn-outline" style={{ fontSize: "0.7rem", padding: "6px 12px" }}>
              ↗ Request Tx
            </a>
          ) : null}
          {v.response_tx_url && isExplorerLink(v.response_tx_url) ? (
            <a href={v.response_tx_url} target="_blank" rel="noreferrer" className="btn-outline" style={{ fontSize: "0.7rem", padding: "6px 12px" }}>
              ↗ Response Tx
            </a>
          ) : null}
        </div>

        {v.last_error ? (
          <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 8, background: "rgba(234,67,53,0.08)", border: "1px solid rgba(234,67,53,0.15)" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--error)" }}>{v.last_error}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
