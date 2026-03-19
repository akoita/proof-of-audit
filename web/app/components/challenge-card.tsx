"use client";

import type { AuditRecord } from "../lib/types";
import {
  challengePathSummary,
  formatEth,
  isExplorerLink,
  shortenHex,
  statusTone,
  titleCase,
} from "../lib/format";

type ChallengeCardProps = { audit: AuditRecord };

export function ChallengeCard({ audit }: ChallengeCardProps) {
  if (!audit.challenge) return null;
  const ch = audit.challenge;

  const statusColor = statusTone(ch.status) === "confirmed" ? "var(--secondary)"
    : statusTone(ch.status) === "warning" ? "var(--tertiary)"
    : "var(--error)";

  const statusBadge = ch.status === "resolved" ? "badge-published"
    : ch.status === "opened" ? "badge-challenged"
    : "badge-draft";

  return (
    <div className="card">
      <div className="card-body">
        <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: "1.1rem" }}>⚔️</span>
          Challenge &amp; Resolution
          <span className={`badge ${statusBadge}`} style={{ marginLeft: "auto", fontSize: "0.55rem" }}>
            {ch.status.toUpperCase()}
          </span>
        </h3>

        {/* Evidence URI */}
        <div className="hash-card" style={{ padding: "10px 14px", marginTop: 14 }}>
          <div className="hash-label">EVIDENCE URI</div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
            <code className="mono" style={{ fontSize: "0.7rem", wordBreak: "break-all" }}>{ch.proof_uri}</code>
            <a href={ch.proof_uri} target="_blank" rel="noreferrer" style={{ flexShrink: 0, marginLeft: 8, color: "var(--primary)", fontSize: "0.7rem" }}>
              View ↗
            </a>
          </div>
        </div>

        {/* Key-value grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 12 }}>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">RESOLUTION PATH</div>
            <div style={{ fontSize: "0.82rem", fontWeight: 600, marginTop: 2, display: "flex", alignItems: "center", gap: 6 }}>
              <span>⚡</span> {titleCase(ch.resolution_path)}
            </div>
          </div>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">CHALLENGE BOND</div>
            <div style={{ fontSize: "0.82rem", fontWeight: 600, marginTop: 2, color: "var(--tertiary)" }}>
              {ch.challenge_bond_wei ? formatEth(ch.challenge_bond_wei) : "n/a"}
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">CHALLENGER</div>
            <div className="mono" style={{ fontSize: "0.7rem", marginTop: 2 }} title={ch.challenger_address ?? ch.challenger}>
              {ch.challenger_address ? shortenHex(ch.challenger_address, 8, 6) : ch.challenger}
            </div>
          </div>
          <div className="hash-card" style={{ padding: "10px 14px" }}>
            <div className="hash-label">CHALLENGE TX</div>
            <div className="mono" style={{ fontSize: "0.7rem", marginTop: 2 }} title={ch.challenge_tx_hash}>
              {shortenHex(ch.challenge_tx_hash, 8, 6)}
            </div>
          </div>
        </div>

        {/* Links */}
        <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
          {ch.challenge_tx_url && isExplorerLink(ch.challenge_tx_url) ? (
            <a href={ch.challenge_tx_url} target="_blank" rel="noreferrer" className="btn-outline" style={{ fontSize: "0.7rem", padding: "6px 12px" }}>
              ↗ Challenge Tx
            </a>
          ) : (
            <span className="muted" style={{ fontSize: "0.65rem", display: "flex", alignItems: "center", gap: 4 }}>
              ✅ Confirmed locally
            </span>
          )}
          {ch.resolve_tx_url && isExplorerLink(ch.resolve_tx_url) ? (
            <a href={ch.resolve_tx_url} target="_blank" rel="noreferrer" className="btn-outline" style={{ fontSize: "0.7rem", padding: "6px 12px" }}>
              ↗ Resolution Tx
            </a>
          ) : null}
        </div>

        {/* Resolution outcome */}
        {ch.resolution ? (
          <div style={{ marginTop: 14, padding: "14px 16px", borderRadius: 10, background: "var(--surface-container-high)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor }} />
              <strong style={{ fontSize: "0.82rem" }}>Resolution: {titleCase(ch.resolution)}</strong>
            </div>
            <p className="muted" style={{ fontSize: "0.72rem", lineHeight: 1.6 }}>
              Resolved by <strong>{ch.resolved_by ?? "arbiter"}</strong> with payout{" "}
              <span style={{ color: "var(--secondary)", fontWeight: 600 }}>
                {ch.payout_wei ? formatEth(ch.payout_wei) : "pending"}
              </span>
            </p>
          </div>
        ) : null}

        {/* Verification details */}
        {ch.verification_summary ? (
          <div style={{ marginTop: 12, padding: "12px 14px", borderRadius: 8, background: "var(--surface-container-low)" }}>
            <div className="hash-label" style={{ marginBottom: 4 }}>
              {(ch.verification_status ?? "verification").toUpperCase()}
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--on-surface)", lineHeight: 1.6 }}>
              {ch.verification_summary}
            </p>
            {ch.verification_detail ? (
              <p className="muted" style={{ fontSize: "0.7rem", marginTop: 6, lineHeight: 1.6 }}>
                {ch.verification_detail}
              </p>
            ) : null}
          </div>
        ) : null}

        {/* Challenge path summary */}
        <p className="muted" style={{ fontSize: "0.7rem", marginTop: 12, lineHeight: 1.5, fontStyle: "italic" }}>
          {challengePathSummary(audit)}
        </p>
      </div>
    </div>
  );
}
