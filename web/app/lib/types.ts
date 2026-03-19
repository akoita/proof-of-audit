export type Finding = {
  finding_id: string;
  title: string;
  severity: string;
  category: string;
  description: string;
  impact: string;
  recommendation: string;
  detector: string;
  confidence: string;
  affected_function?: string | null;
  source_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  evidence_uri?: string | null;
};

export type AuditorReputation = {
  score: number;
  band: "provisional" | "trusted" | "mixed" | "contested";
  resolved_challenge_count: number;
  challenge_rejected_count: number;
  challenge_upheld_count: number;
  open_challenge_count: number;
  published_claim_count: number;
  draft_claim_count: number;
  last_resolved_at?: string | null;
  formula: string;
};

export type AuditorProfile = {
  id: string;
  name: string;
  version: string;
  manifest_schema: string;
  service_type: string;
  description: string;
  capabilities: string[];
  operator: string;
  resolution_policy: string;
  reputation?: AuditorReputation | null;
};

export type AuditorServiceRecord = {
  service_id: string;
  name: string;
  manifest_schema: string;
  manifest_hash: string;
  registration_kind: string;
  registration_uri: string;
  agent_id?: number | null;
  agent_registry?: string | null;
  identity_source?: string | null;
  capability: string;
  discovery_path: string;
  submit_path: string;
  publish_path_template: string;
  challenge_path_template: string;
  network: string;
  registry_contract_address?: string | null;
  validation_registry_address?: string | null;
  validation_source?: string | null;
  validation_request_path_template: string;
  validation_response_path_template: string;
  submission_modes: string[];
  resolution_modes: string[];
  deterministic_resolution_supported: boolean;
  manual_fallback_supported: boolean;
  reputation?: AuditorReputation | null;
};

export type PublicContractConfig = {
  network: string;
  chain_id: number;
  contract_address: string | null;
  explorer_base_url: string;
  arbiter: string | null;
  auditor: AuditorProfile;
  auditor_service: AuditorServiceRecord;
  required_stake_wei: number;
  required_challenge_bond_wei: number;
  challenge_window_seconds: number;
  deployment_ready: boolean;
};

export type InputKind =
  | "deployed_address"
  | "demo_fixture"
  | "source_bundle"
  | "repository_url";

export type Submission = {
  input_kind: InputKind;
  chain_id?: number | null;
  contract_address?: string | null;
  fixture_id?: string | null;
  entry_contract?: string | null;
  source_bundle_uri?: string | null;
  source_bundle_label?: string | null;
  repository_url?: string | null;
};

export type AuditRecord = {
  id: string;
  contract_address: string;
  target_key: string;
  target_auditor_key: string;
  agent: AuditorProfile;
  submission: Submission;
  submitted_by: string;
  status: string;
  created_at: string;
  report: {
    benchmark_id: string;
    contract_address: string;
    summary: string;
    findings: Finding[];
    supported_checks: string[];
    confidence: string;
    report_hash: string;
    metadata_hash: string;
    max_severity: number;
    finding_count: number;
    severity_breakdown: Record<string, number>;
  };
  onchain: null | {
    audit_id?: number;
    network: string;
    chain_id: number;
    contract_address?: string | null;
    explorer_base_url: string;
    agent_identity: string;
    agent_name?: string | null;
    agent_version?: string | null;
    stake_wei: number;
    report_hash: string;
    metadata_hash: string;
    max_severity: number;
    finding_count: number;
    publish_tx_hash: string;
    publish_tx_url?: string | null;
  };
  challenge: null | {
    challenger: string;
    challenger_address?: string | null;
    proof_uri: string;
    submitted_at: string;
    verifier: string;
    status: string;
    resolution_path: string;
    verification_status?: string | null;
    verification_summary?: string | null;
    verification_detail?: string | null;
    verification_case_id?: string | null;
    resolution?: string | null;
    resolved_at?: string | null;
    resolved_by?: string | null;
    beneficiary_address?: string | null;
    payout_wei?: number | null;
    challenge_hash?: string | null;
    challenge_bond_wei?: number | null;
    chain_id?: number | null;
    challenge_tx_hash: string;
    challenge_tx_url?: string | null;
    resolve_tx_hash?: string | null;
    resolve_tx_url?: string | null;
  };
  validation: null | {
    status: string;
    registry_address: string;
    source: string;
    agent_id: number;
    request_uri: string;
    request_hash: string;
    validator_address: string;
    request_tx_hash?: string | null;
    request_tx_url?: string | null;
    response?: number | null;
    response_tag?: string | null;
    response_uri?: string | null;
    response_hash?: string | null;
    response_tx_hash?: string | null;
    response_tx_url?: string | null;
    linked_resolution?: string | null;
    linked_resolution_path?: string | null;
    last_error?: string | null;
  };
};

export type TargetComparisonResponse = {
  target_contract: string;
  target_key: string;
  summary: {
    claim_count: number;
    published_count: number;
    challenged_count: number;
    resolved_count: number;
    max_severity: number;
  };
  items: AuditRecord[];
};

export type DemoFixture = {
  id: string;
  label: string;
  contract_name: string;
  entry_contract: string;
  benchmark_id: string;
  address: string;
  challenge_proof_uri: string;
  note: string;
  source_path: string;
};
