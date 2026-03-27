"use client";

import type { AuditRecord, ChallengePolicy, ChallengePolicyPresetId, PublicContractConfig } from "../lib/types";
import { formatEth, publishBlockedReason, policySummary, policyOpennessLabel } from "../lib/format";
import { PolicySelector } from "./policy-selector";

type ActionsPanelProps = {
  audit: AuditRecord;
  config: PublicContractConfig | null;
  publicationMode?: string | null;
  proofUri: string;
  isPending: boolean;
  activeAction: string | null;
  publishStake: number;
  challengeBond: number;
  selectedPolicyPresetId: ChallengePolicyPresetId;
  onProofUriChange: (v: string) => void;
  onPublish: () => void;
  onChallenge: () => void;
  onPolicyChange: (presetId: ChallengePolicyPresetId, policy: ChallengePolicy) => void;
};

export function ActionsPanel({
  audit,
  config,
  publicationMode,
  proofUri,
  isPending,
  activeAction,
  publishStake,
  challengeBond,
  selectedPolicyPresetId,
  onProofUriChange,
  onPublish,
  onChallenge,
  onPolicyChange,
}: ActionsPanelProps) {
  if (audit.status !== "draft" && audit.status !== "published") return null;
  const isApiMediated = publicationMode === "api_mediated";
  const networkLabel = config?.network ?? "this deployment";
  const publishRestriction = publishBlockedReason(audit);

  /* Challenge scope preflight for published audits */
  const challengePolicy = audit.onchain?.challenge_policy ?? null;

  return (
    <div className="action-cta" style={{ marginTop: 20 }}>
      {audit.status === "draft" ? (
        <>
          <div className="action-cta-info">
            <div className="action-cta-icon">🚀</div>
            <div>
              <h4>{publishRestriction ? "Publish Unavailable" : "Ready for Protocol Staking?"}</h4>
              <p>
                {publishRestriction ?? (isApiMediated
                  ? `This ${networkLabel} release publishes through an API signer. The backend wallet must hold ${formatEth(Number(publishStake))} plus gas; the connected browser wallet is not used for publish yet.`
                  : `Stake ${formatEth(Number(publishStake))} and move this draft to the publication phase to earn reputation.`)}
              </p>
            </div>
          </div>

          {/* ── Policy Selector ── */}
          {!publishRestriction ? (
            <PolicySelector
              selectedPresetId={selectedPolicyPresetId}
              onSelect={onPolicyChange}
            />
          ) : null}

          <button
            type="button"
            className="cta-gradient"
            disabled={isPending || publishRestriction !== null}
            onClick={onPublish}
            data-testid="publish-btn"
            style={{ marginTop: 14 }}
          >
            {publishRestriction
              ? "Publish Unavailable"
              : activeAction ?? (isApiMediated ? "Publish via API Signer" : "Prepare for Publication")}
          </button>
        </>
      ) : (
        <>
          <div className="action-cta-info">
            <div className="action-cta-icon">⚖</div>
            <div>
              <h4>Challenge This Claim</h4>
              <p>
                {isApiMediated
                  ? `This ${networkLabel} release opens challenges through the API signer. The backend wallet must hold ${formatEth(Number(challengeBond))} plus gas for the challenge bond.`
                  : `Bond ${formatEth(Number(challengeBond))} to dispute this audit with a proof of error.`}
              </p>
            </div>
          </div>

          {/* ── Scope Preflight Notice ── */}
          {challengePolicy ? (
            <div
              style={{
                marginTop: 12,
                padding: "12px 16px",
                borderRadius: 12,
                background: "var(--surface-container-low)",
                border: "1px solid rgba(67,70,85,0.15)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                <span>📋</span>
                <strong style={{ fontSize: "0.78rem" }}>Active Challenge Policy</strong>
                <span
                  className="badge"
                  style={{
                    fontSize: "0.5rem",
                    marginLeft: "auto",
                    background:
                      policyOpennessLabel(challengePolicy) === "Open"
                        ? "rgba(76,175,80,0.15)"
                        : policyOpennessLabel(challengePolicy) === "Restrictive"
                          ? "rgba(229,57,53,0.15)"
                          : "rgba(255,193,7,0.15)",
                    color:
                      policyOpennessLabel(challengePolicy) === "Open"
                        ? "var(--secondary)"
                        : policyOpennessLabel(challengePolicy) === "Restrictive"
                          ? "var(--error, #e53935)"
                          : "var(--tertiary)",
                  }}
                >
                  {policyOpennessLabel(challengePolicy)}
                </span>
              </div>
              <p className="muted" style={{ fontSize: "0.68rem", lineHeight: 1.5, margin: 0 }}>
                {policySummary(challengePolicy)}
              </p>
              {challengePolicy.requires_material_incorrectness ? (
                <p
                  style={{
                    fontSize: "0.65rem",
                    color: "var(--tertiary)",
                    marginTop: 6,
                    fontWeight: 500,
                  }}
                >
                  ⚠ This policy requires evidence of material incorrectness for admissibility.
                </p>
              ) : null}
            </div>
          ) : null}

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
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
