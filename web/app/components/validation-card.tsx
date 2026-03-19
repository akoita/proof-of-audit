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

  return (
    <div className="onchain-card">
      <div className="section-heading">
        <p>Validation bridge</p>
        <span data-tone={statusTone(v.status)}>{v.status}</span>
      </div>
      <p className="muted">
        Mirrors this audit into {formatIdentitySource(v.source)} validation infrastructure.
      </p>
      <div className="metadata-grid">
        <div><span>Agent ID</span><strong>{v.agent_id}</strong></div>
        <div>
          <span>Validator</span>
          <strong title={v.validator_address}>{shortenHex(v.validator_address, 10, 8)}</strong>
        </div>
        <div>
          <span>Request hash</span>
          <strong title={v.request_hash}>{shortenHex(v.request_hash, 12, 8)}</strong>
        </div>
      </div>
      <div className="metadata-grid">
        <div>
          <span>Registry</span>
          <strong title={v.registry_address}>{shortenHex(v.registry_address, 10, 8)}</strong>
        </div>
        <div>
          <span>Response</span>
          <strong>
            {v.response === null || v.response === undefined ? "pending" : `${v.response}/100`}
          </strong>
        </div>
        <div>
          <span>Tag</span>
          <strong>{v.response_tag ?? "pending"}</strong>
        </div>
      </div>
      <div className="inline-links">
        <a href={v.request_uri} target="_blank" rel="noreferrer">View request</a>
        {v.response_uri ? (
          <a href={v.response_uri} target="_blank" rel="noreferrer">View response</a>
        ) : null}
        {v.request_tx_url && isExplorerLink(v.request_tx_url) ? (
          <a href={v.request_tx_url} target="_blank" rel="noreferrer">Request tx</a>
        ) : null}
        {v.response_tx_url && isExplorerLink(v.response_tx_url) ? (
          <a href={v.response_tx_url} target="_blank" rel="noreferrer">Response tx</a>
        ) : null}
      </div>
      {v.last_error ? <p className="muted">{v.last_error}</p> : null}
    </div>
  );
}
