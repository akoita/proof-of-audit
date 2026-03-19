"use client";

import type { AuditRecord, PublicContractConfig } from "../lib/types";
import {
  challengePathLabel,
  challengePathSummary,
  formatEth,
  suggestedProofUriForBenchmark,
} from "../lib/format";

type ActionsPanelProps = {
  audit: AuditRecord;
  config: PublicContractConfig | null;
  proofUri: string;
  isPending: boolean;
  activeAction: string | null;
  publishStake: number;
  challengeBond: number;
  onProofUriChange: (value: string) => void;
  onPublish: () => void;
  onChallenge: () => void;
};

export function ActionsPanel({
  audit,
  config,
  proofUri,
  isPending,
  activeAction,
  publishStake,
  challengeBond,
  onProofUriChange,
  onPublish,
  onChallenge,
}: ActionsPanelProps) {
  const canPublish =
    !isPending &&
    audit.status === "draft" &&
    audit.submission.input_kind !== "source_bundle" &&
    config?.deployment_ready;

  const canChallenge =
    !isPending &&
    audit.status === "published" &&
    config?.deployment_ready;

  return (
    <div className="action-row">
      <div className="action-card">
        <span>Publish claim</span>
        <strong>Stake {formatEth(publishStake)}</strong>
        <p className="muted">
          {audit.submission.input_kind === "source_bundle"
            ? "Deploy the source bundle first, then resubmit as a deployed address."
            : `${audit.agent.name} commits this judgment on-chain.`}
        </p>
        <button type="button" onClick={onPublish} disabled={!canPublish}>
          {isPending && activeAction?.includes("publish")
            ? "Publishing…"
            : "Stake and publish"}
        </button>
      </div>
      <div className="action-card action-card-wide">
        <span>{challengePathLabel(audit)}</span>
        <strong>Bond {formatEth(challengeBond)}</strong>
        <input
          value={proofUri}
          onChange={(e) => onProofUriChange(e.target.value)}
          disabled={!canChallenge}
        />
        <button type="button" onClick={onChallenge} disabled={!canChallenge}>
          {isPending && activeAction?.includes("challenge")
            ? "Challenging…"
            : "Open challenge"}
        </button>
        <p className="muted">
          Evidence: <code>{suggestedProofUriForBenchmark(audit.report.benchmark_id)}</code>
        </p>
        <p className="muted">{challengePathSummary(audit)}</p>
      </div>
    </div>
  );
}
