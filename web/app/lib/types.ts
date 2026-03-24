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

export type ChallengeClaim = {
  schema_version: string;
  claim_type: string;
  basis: string;
  confidence: string;
  affected_surfaces: string[];
  preconditions: string[];
  demonstrated_effect?: string | null;
  claimed_impact?: string | null;
  supporting_signals: string[];
};

export type VerificationFindingMatch = {
  finding_id: string;
  relationship: string;
  confidence: string;
  rationale?: string | null;
  score?: number | null;
};

export type VerificationDossier = {
  schema_version: string;
  verifier_version: string;
  evidence_type: string;
  integrity: {
    status: string;
    committed_evidence_hash?: string | null;
  };
  execution: {
    status: string;
    execution_env?: string | null;
    backend?: string | null;
    isolation_level?: string | null;
    source_path?: string | null;
    fork_block_number?: number | null;
  };
  claim?: ChallengeClaim | null;
  comparison: {
    status: string;
    confidence: string;
    rationale?: string | null;
    matched_finding_ids: string[];
    matched_findings: VerificationFindingMatch[];
    unmatched_signals: string[];
    disagreement_status: string;
    disagreement_detail?: string | null;
  };
  policy: {
    status: string;
    advisory_only: boolean;
    recommended_resolution?: string | null;
    abstained: boolean;
    confidence: string;
    rationale?: string | null;
  };
  model_metadata: Record<string, string | number | boolean | null>;
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
  registration_type: string;
  registration_endpoint: string;
  registration_uri: string;
  agent_id?: number | null;
  agent_registry?: string | null;
  identity_source?: string | null;
  capability: string;
  discovery_path: string;
  submit_path: string;
  execution_mode: string;
  execution_endpoint?: string | null;
  publish_path_template: string;
  challenge_path_template: string;
  network: string;
  active: boolean;
  supported_trust: string[];
  settlement_mode: string;
  publication_mode: string;
  staking_adapter_kind: string;
  staking_adapter_address?: string | null;
  staking_adapter_method?: string | null;
  publication_scope: string;
  registry_contract_address?: string | null;
  validation_registry_address?: string | null;
  validation_source?: string | null;
  validation_request_path_template: string;
  validation_response_path_template: string;
  reputation_registry_address?: string | null;
  reputation_source?: string | null;
  reputation_path_template: string;
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

export type SourceBundleUpload = {
  original_filename: string;
  source_bundle_uri: string;
  storage_backend?: string;
  source_bundle_label?: string | null;
  entry_contract?: string | null;
};

export type InputKind =
  | "deployed_address"
  | "demo_fixture"
  | "source_bundle"
  | "repository_url";

export type Submission = {
  input_kind: InputKind;
  service_id?: string | null;
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
  auditor_service: AuditorServiceRecord;
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
    evidence_hash?: string | null;
    evidence_type?: "deterministic_fixture" | "executable_test";
    execution_env?: "foundry" | null;
    evidence_manifest?: Record<string, string | number | boolean | null> | null;
    submitted_at: string;
    verifier: string;
    status: string;
    resolution_path: string;
    verification_status?: string | null;
    verification_summary?: string | null;
    verification_detail?: string | null;
    verification_case_id?: string | null;
    advisory_verdict?: "upheld" | "rejected" | null;
    execution_log?: string | null;
    matched_findings: string[];
    unmatched_findings: string[];
    verification_dossier?: VerificationDossier | null;
    verification_dossier_path?: string | null;
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
