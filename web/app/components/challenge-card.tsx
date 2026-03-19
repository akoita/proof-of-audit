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

  return (
    <div className="challenge-card">
      <div className="section-heading">
        <p>Challenge and resolution</p>
        <span data-testid="challenge-status" data-tone={statusTone(ch.status)}>
          {ch.status}
        </span>
      </div>
      <p className="muted">{ch.proof_uri}</p>
      <div className="metadata-grid">
        <div>
          <span>Path</span>
          <strong>{titleCase(ch.resolution_path)}</strong>
        </div>
        <div>
          <span>Challenger</span>
          <strong title={ch.challenger_address ?? ""}>
            {ch.challenger_address ? shortenHex(ch.challenger_address, 10, 8) : ch.challenger}
          </strong>
        </div>
        <div>
          <span>Bond</span>
          <strong>{ch.challenge_bond_wei ? formatEth(ch.challenge_bond_wei) : "n/a"}</strong>
        </div>
        <div>
          <span>Challenge tx</span>
          <strong title={ch.challenge_tx_hash}>{shortenHex(ch.challenge_tx_hash, 12, 8)}</strong>
        </div>
      </div>
      <div className="inline-links">
        {ch.challenge_tx_url && isExplorerLink(ch.challenge_tx_url) ? (
          <a href={ch.challenge_tx_url} target="_blank" rel="noreferrer">View challenge tx</a>
        ) : (
          <span className="muted">Challenge tx confirmed locally.</span>
        )}
        {ch.resolve_tx_url && isExplorerLink(ch.resolve_tx_url) ? (
          <a href={ch.resolve_tx_url} target="_blank" rel="noreferrer">View resolution tx</a>
        ) : null}
      </div>
      {ch.resolution ? (
        <p className="muted">
          Resolution {ch.resolution} by {ch.resolved_by ?? "arbiter"} with payout{" "}
          {ch.payout_wei ? formatEth(ch.payout_wei) : "pending"}.
        </p>
      ) : null}
      <p className="muted">{challengePathSummary(audit)}</p>
      {ch.verification_summary ? (
        <p className="muted">
          {ch.verification_status ?? "verification"}: {ch.verification_summary}
        </p>
      ) : null}
      {ch.verification_detail ? <p className="muted">{ch.verification_detail}</p> : null}
    </div>
  );
}
