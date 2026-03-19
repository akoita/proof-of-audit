import type { AuditRecord, AuditorProfile, AuditorReputation, InputKind } from "./types";

export function formatEth(wei: number): string {
  return `${(wei / 1e18).toFixed(3)} ETH`;
}

export function titleCase(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function shortenHex(value: string, start = 6, end = 4): string {
  if (value.length <= start + end + 3) {
    return value;
  }
  return `${value.slice(0, start)}...${value.slice(-end)}`;
}

export function formatWindow(seconds: number): string {
  if (seconds % 86400 === 0) return `${seconds / 86400}d`;
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  return `${seconds}s`;
}

export function formatIdentitySource(value: string | null | undefined): string {
  switch (value) {
    case "erc8004-official":
      return "Official ERC-8004";
    case "project-local-custom":
      return "Local fallback";
    default:
      return "Unspecified path";
  }
}

export function formatValidationSource(value: string | null | undefined): string {
  switch (value) {
    case "erc8004-official":
      return "Official ERC-8004";
    case "project-local-adapter":
      return "Local adapter";
    default:
      return "Unspecified path";
  }
}

export function reputationLabel(reputation: AuditorReputation | null | undefined): string {
  if (!reputation) return "—";
  return `${reputation.score}/100 ${titleCase(reputation.band)}`;
}

export function isExplorerLink(url: string | null | undefined): url is string {
  if (!url) return false;
  return !url.includes("127.0.0.1") && !url.includes("localhost");
}

export function addressUrl(
  baseUrl: string | null | undefined,
  address: string | null | undefined,
): string | null {
  if (!isExplorerLink(baseUrl) || !address) return null;
  return `${baseUrl}/address/${address}`;
}

export function statusTone(status: string) {
  switch (status) {
    case "published":
    case "resolved":
    case "requested":
    case "responded":
      return "confirmed";
    case "rejected":
      return "confirmed";
    case "upheld":
    case "challenged":
    case "opened":
    case "request_failed":
    case "response_failed":
      return "warning";
    case "draft":
    default:
      return "neutral";
  }
}

export function lifecycleLabel(audit: AuditRecord): string {
  if (audit.status === "resolved" && audit.challenge?.resolution) {
    return `Challenge ${audit.challenge.resolution}`;
  }
  if (audit.challenge) return "Challenge opened";
  if (audit.onchain) return "Published on-chain";
  return "Draft report";
}

export function submissionModeLabel(mode: InputKind): string {
  switch (mode) {
    case "demo_fixture":
      return "Demo fixture";
    case "source_bundle":
      return "Source bundle";
    case "repository_url":
      return "Repository";
    default:
      return "Deployed address";
  }
}

export function submissionTargetLabel(audit: AuditRecord): string {
  if (audit.submission.input_kind === "demo_fixture") {
    return audit.submission.entry_contract ?? audit.submission.fixture_id ?? audit.report.benchmark_id;
  }
  if (audit.submission.input_kind === "source_bundle") {
    return audit.submission.entry_contract ?? audit.submission.source_bundle_label ?? "source bundle";
  }
  return shortenHex(audit.contract_address, 8, 6);
}

export function agentVersionLabel(agent: AuditorProfile | null | undefined): string {
  if (!agent) return "loading";
  return `${agent.name} v${agent.version}`;
}

export function severityRankLabel(rank: number): string {
  switch (rank) {
    case 4: return "Critical";
    case 3: return "High";
    case 2: return "Medium";
    case 1: return "Low";
    default: return "Info";
  }
}

export function relativeTimeLabel(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function suggestedProofUriForBenchmark(benchmarkId: string): string {
  switch (benchmarkId) {
    case "clean-vault":
      return "ipfs://clean-vault/missed-reentrancy";
    case "reentrancy-bank":
      return "ipfs://reentrancy-bank/withdraw-drain";
    case "admin-setter":
      return "ipfs://admin-setter/unauthorized-admin-change";
    case "dual-risk-vault":
      return "ipfs://dual-risk-vault/owner-takeover";
    case "unchecked-treasury":
      return "ipfs://unchecked-treasury/unchecked-call-failure";
    default:
      return "ipfs://benchmark-proof";
  }
}

export function challengePathLabel(audit: AuditRecord): string {
  if (!audit.challenge) return "Deterministic path ready";
  return audit.challenge.resolution_path === "deterministic"
    ? "Deterministic path"
    : "Manual fallback";
}

export function challengePathSummary(audit: AuditRecord): string {
  if (!audit.challenge) {
    return "Curated fixture evidence auto-resolves known benchmark cases on-chain.";
  }
  if (audit.challenge.resolution_path === "deterministic") {
    return "The verifier matched curated benchmark evidence and completed on-chain resolution automatically.";
  }
  return "The verifier could not confirm a curated case. Challenge is on the manual fallback path.";
}
