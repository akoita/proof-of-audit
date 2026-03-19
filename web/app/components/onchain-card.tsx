"use client";

import type { AuditRecord } from "../lib/types";
import { addressUrl, formatEth, isExplorerLink, shortenHex } from "../lib/format";

type OnchainCardProps = { audit: AuditRecord };

export function OnchainCard({ audit }: OnchainCardProps) {
  if (!audit.onchain) return null;
  const oc = audit.onchain;

  return (
    <div className="onchain-card">
      <div className="section-heading">
        <p>On-chain commitment</p>
        <span data-tone="confirmed">{oc.network}</span>
      </div>
      <p className="muted">
        {oc.agent_name ?? audit.agent.name} ({oc.agent_identity}) staked{" "}
        {formatEth(oc.stake_wei)} behind this judgment.
      </p>
      <div className="metadata-grid">
        <div>
          <span>Audit ID</span>
          <strong>{oc.audit_id ?? "pending"}</strong>
        </div>
        <div>
          <span>Contract</span>
          <strong title={oc.contract_address ?? ""}>
            {oc.contract_address ? shortenHex(oc.contract_address, 10, 8) : "—"}
          </strong>
        </div>
        <div>
          <span>Publish tx</span>
          <strong title={oc.publish_tx_hash}>
            {shortenHex(oc.publish_tx_hash, 12, 8)}
          </strong>
        </div>
      </div>
      <div className="inline-links">
        {oc.publish_tx_url && isExplorerLink(oc.publish_tx_url) ? (
          <a href={oc.publish_tx_url} target="_blank" rel="noreferrer">View publish tx</a>
        ) : (
          <span className="muted">Publish tx confirmed locally.</span>
        )}
        {addressUrl(oc.explorer_base_url, oc.contract_address ?? null) ? (
          <a
            href={addressUrl(oc.explorer_base_url, oc.contract_address ?? null) ?? undefined}
            target="_blank"
            rel="noreferrer"
          >
            View registry
          </a>
        ) : null}
      </div>
    </div>
  );
}
