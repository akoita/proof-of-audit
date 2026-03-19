"use client";

import type { AuditRecord, PublicContractConfig } from "../lib/types";
import { formatEth } from "../lib/format";

type ActionsPanelProps = {
  audit: AuditRecord;
  config: PublicContractConfig | null;
  proofUri: string;
  isPending: boolean;
  activeAction: string | null;
  publishStake: number;
  challengeBond: number;
  onProofUriChange: (v: string) => void;
  onPublish: () => void;
  onChallenge: () => void;
};

export function ActionsPanel({
  audit,
  proofUri,
  isPending,
  activeAction,
  publishStake,
  challengeBond,
  onProofUriChange,
  onPublish,
  onChallenge,
}: ActionsPanelProps) {
  if (audit.status !== "draft" && audit.status !== "published") return null;

  return (
    <div className="action-cta" style={{ marginTop: 20 }}>
      {audit.status === "draft" ? (
        <>
          <div className="action-cta-info">
            <div className="action-cta-icon">🚀</div>
            <div>
              <h4>Ready for Protocol Staking?</h4>
              <p>
                Stake {formatEth(Number(publishStake))} and move this draft to the publication
                phase to earn reputation.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="cta-gradient"
            disabled={isPending}
            onClick={onPublish}
            data-testid="publish-btn"
          >
            {activeAction ?? "Prepare for Publication"}
          </button>
        </>
      ) : (
        <>
          <div className="action-cta-info">
            <div className="action-cta-icon">⚖</div>
            <div>
              <h4>Challenge This Claim</h4>
              <p>
                Bond {formatEth(Number(challengeBond))} to dispute this audit with a proof of
                error.
              </p>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input
              className="input-field mono"
              placeholder="ipfs://proof-uri..."
              value={proofUri}
              onChange={(e) => onProofUriChange(e.target.value)}
              style={{ width: 280 }}
            />
            <button
              type="button"
              className="cta-gradient"
              disabled={isPending || !proofUri}
              onClick={onChallenge}
              data-testid="challenge-btn"
            >
              {activeAction ?? "Open Challenge"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
