from __future__ import annotations

import base64
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuditorServiceEndpointModel(BaseModel):
    name: str
    endpoint: str
    version: str | None = None


class AuditorRegistrationRefModel(BaseModel):
    agentId: int
    agentRegistry: str


class AuditorExtensionModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    version: str
    serviceType: str
    capabilities: list[str]
    operator: str
    resolutionPolicy: str


class AuditorRegistrationDocumentModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str
    name: str
    description: str
    image: str
    services: list[AuditorServiceEndpointModel]
    x402Support: bool
    active: bool
    registrations: list[AuditorRegistrationRefModel]
    supportedTrust: list[str]
    x_proof_of_audit: AuditorExtensionModel = Field(
        alias="x-proof-of-audit",
        serialization_alias="x-proof-of-audit",
    )


class AuditorProfileModel(BaseModel):
    type: str
    id: str
    name: str
    version: str
    manifest_schema: str
    service_type: str
    description: str
    image: str
    services: list[AuditorServiceEndpointModel]
    x402Support: bool
    active: bool
    registrations: list[AuditorRegistrationRefModel]
    supportedTrust: list[str]
    capabilities: list[str]
    operator: str
    resolution_policy: str
    reputation: "AuditorReputationModel | None" = None


class AuditorServiceRecordModel(BaseModel):
    service_id: str
    name: str
    manifest_schema: str
    manifest_hash: str
    registration_kind: str
    registration_type: str
    registration_endpoint: str
    registration_uri: str
    agent_id: int | None = None
    agent_registry: str | None = None
    identity_source: str | None = None
    capability: str
    discovery_path: str
    submit_path: str
    execution_mode: str
    execution_endpoint: str | None = None
    publish_path_template: str
    challenge_path_template: str
    network: str
    active: bool
    supported_trust: list[str]
    settlement_mode: str
    publication_mode: str
    staking_adapter_kind: str
    staking_adapter_address: str | None = None
    staking_adapter_method: str | None = None
    publication_scope: str
    registry_contract_address: str | None = None
    validation_registry_address: str | None = None
    validation_source: str | None = None
    validation_request_path_template: str
    validation_response_path_template: str
    reputation_registry_address: str | None = None
    reputation_source: str | None = None
    reputation_path_template: str
    submission_modes: list[str]
    resolution_modes: list[str]
    deterministic_resolution_supported: bool
    manual_fallback_supported: bool
    reputation: "AuditorReputationModel | None" = None


class AuditorServiceListResponse(BaseModel):
    items: list[AuditorServiceRecordModel]


class FindingModel(BaseModel):
    finding_id: str
    title: str
    severity: str
    category: str
    description: str
    impact: str
    recommendation: str
    detector: str
    confidence: str
    affected_function: str | None = None
    source_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    evidence_uri: str | None = None


class NormalizedFindingModel(BaseModel):
    schema_version: str = "normalized-audit-finding/v1"
    finding_id: str
    vulnerability_classes: list[str] = Field(default_factory=list)
    affected_surfaces: list[str] = Field(default_factory=list)
    detector_families: list[str] = Field(default_factory=list)
    severity: str
    impact_summary: str
    preconditions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class AuditReportModel(BaseModel):
    benchmark_id: str
    contract_address: str
    summary: str
    findings: list[FindingModel]
    normalized_findings: list[NormalizedFindingModel] = Field(default_factory=list)
    supported_checks: list[str]
    confidence: str
    report_hash: str
    metadata_hash: str
    max_severity: int
    finding_count: int
    severity_breakdown: dict[str, int]


class ChallengePolicyModel(BaseModel):
    policy_version: Literal["challenge-policy/v1"] = "challenge-policy/v1"
    allowed_evidence_types: list[Literal["deterministic_fixture", "executable_test"]] = (
        Field(default_factory=lambda: ["deterministic_fixture", "executable_test"])
    )
    min_severity_threshold: str = "info"
    allow_informational_only: bool = True
    requires_material_incorrectness: bool = False
    admissibility_mode: Literal["broad", "strict"] = "broad"

    @model_validator(mode="after")
    def validate_policy_fields(self) -> "ChallengePolicyModel":
        normalized_types = sorted({str(item) for item in self.allowed_evidence_types})
        if not normalized_types:
            raise ValueError("allowed_evidence_types must include at least one evidence type")
        self.allowed_evidence_types = normalized_types
        normalized_threshold = str(self.min_severity_threshold or "info").strip().lower()
        if normalized_threshold == "informational":
            normalized_threshold = "info"
        if normalized_threshold not in {"info", "low", "medium", "high", "critical"}:
            raise ValueError(
                "min_severity_threshold must be one of info, low, medium, high, or critical"
            )
        self.min_severity_threshold = normalized_threshold
        return self


class OnchainPublicationModel(BaseModel):
    audit_id: int | None = None
    request_id: int | None = None
    request_claim_id: int | None = None
    publication_mode: str | None = None
    claim_state: str | None = None
    published_at: str | None = None
    network: str
    chain_id: int
    contract_address: str | None = None
    explorer_base_url: str
    agent_identity: str
    agent_name: str | None = None
    agent_version: str | None = None
    stake_wei: int
    report_hash: str
    metadata_hash: str
    max_severity: int
    finding_count: int
    publish_tx_hash: str
    publish_tx_url: str | None = None
    claim_tx_hash: str | None = None
    claim_tx_url: str | None = None
    agent_id: int | None = None
    agent_registry: str | None = None
    auditor_address: str | None = None
    challenge_policy: ChallengePolicyModel | None = None


class ChallengeModel(BaseModel):
    challenger: str
    challenger_address: str | None = None
    proof_uri: str
    evidence_hash: str | None = None
    evidence_type: Literal["deterministic_fixture", "executable_test"] = (
        "deterministic_fixture"
    )
    execution_env: Literal["foundry"] | None = None
    evidence_manifest: "ExecutableEvidenceManifestModel | None" = None
    submitted_at: str
    verifier: str
    status: str
    resolution_path: str
    verification_status: str | None = None
    verification_summary: str | None = None
    verification_detail: str | None = None
    verification_case_id: str | None = None
    policy_admissibility_status: str | None = None
    policy_admissibility_rationale: str | None = None
    advisory_verdict: Literal["upheld", "rejected"] | None = None
    execution_log: str | None = None
    matched_findings: list[str] = Field(default_factory=list)
    unmatched_findings: list[str] = Field(default_factory=list)
    verification_dossier: "VerificationDossierModel | None" = None
    verification_dossier_path: str | None = None
    resolution: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    beneficiary_address: str | None = None
    payout_wei: int | None = None
    challenge_hash: str | None = None
    challenge_bond_wei: int | None = None
    chain_id: int | None = None
    challenge_tx_hash: str
    challenge_tx_url: str | None = None
    resolve_tx_hash: str | None = None
    resolve_tx_url: str | None = None


class ValidationTrailModel(BaseModel):
    status: str
    registry_address: str
    source: str
    agent_id: int
    request_uri: str
    request_hash: str
    validator_address: str
    request_tx_hash: str | None = None
    request_tx_url: str | None = None
    response: int | None = None
    response_tag: str | None = None
    response_uri: str | None = None
    response_hash: str | None = None
    response_tx_hash: str | None = None
    response_tx_url: str | None = None
    linked_resolution: str | None = None
    linked_resolution_path: str | None = None
    last_error: str | None = None


class ReputationTrailModel(BaseModel):
    status: str
    registry_address: str
    source: str
    agent_id: int
    claim_uri: str
    claim_hash: str
    stake_wei: int
    claim_tx_hash: str | None = None
    claim_tx_url: str | None = None
    claim_confirmed: bool | None = None
    resolution_uri: str | None = None
    resolution_hash: str | None = None
    resolution_tx_hash: str | None = None
    resolution_tx_url: str | None = None
    linked_resolution: str | None = None
    last_error: str | None = None


class ExecutionArtifactModel(BaseModel):
    backend: str
    mode: str
    status: str
    source: str
    live_attempted: bool
    fallback_used: bool
    task_prompt: str | None = None
    workspace_dir: str | None = None
    source_path: str | None = None
    report_path: str | None = None
    run_id: str | None = None
    run_dir: str | None = None
    status_url: str | None = None
    logs_url: str | None = None
    source_digest: str | None = None
    profile_id: str | None = None
    provider: str | None = None
    model: str | None = None
    error: str | None = None


class ChallengeClaimModel(BaseModel):
    schema_version: str = "challenge-claim/v1"
    claim_type: str
    basis: str
    confidence: str = "unknown"
    affected_surfaces: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    demonstrated_effect: str | None = None
    claimed_impact: str | None = None
    supporting_signals: list[str] = Field(default_factory=list)


class VerificationIntegrityModel(BaseModel):
    status: str
    committed_evidence_hash: str | None = None


class VerificationExecutionModel(BaseModel):
    status: str
    execution_env: str | None = None
    backend: str | None = None
    isolation_level: str | None = None
    source_path: str | None = None
    fork_block_number: int | None = None


class VerificationFindingMatchModel(BaseModel):
    finding_id: str
    relationship: str
    confidence: str = "unknown"
    rationale: str | None = None
    score: float | None = None


class VerificationComparisonModel(BaseModel):
    status: str
    confidence: str = "unknown"
    rationale: str | None = None
    matched_finding_ids: list[str] = Field(default_factory=list)
    matched_findings: list[VerificationFindingMatchModel] = Field(default_factory=list)
    unmatched_signals: list[str] = Field(default_factory=list)
    disagreement_status: str = "not_checked"
    disagreement_detail: str | None = None


class VerificationPolicyModel(BaseModel):
    status: str
    advisory_only: bool = False
    recommended_resolution: str | None = None
    abstained: bool = False
    confidence: str = "unknown"
    rationale: str | None = None
    admissibility_status: str | None = None
    effective_policy: ChallengePolicyModel | None = None


class VerificationDossierModel(BaseModel):
    schema_version: str = "challenge-verifier-dossier/v1"
    verifier_version: str
    evidence_type: str
    integrity: VerificationIntegrityModel
    execution: VerificationExecutionModel
    claim: ChallengeClaimModel | None = None
    comparison: VerificationComparisonModel
    policy: VerificationPolicyModel
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class AuditRecordModel(BaseModel):
    id: str
    contract_address: str
    target_key: str
    target_auditor_key: str
    agent: AuditorProfileModel
    auditor_service: AuditorServiceRecordModel
    submission: "AuditSubmissionModel"
    submitted_by: str
    status: str
    created_at: str
    report: AuditReportModel
    execution: ExecutionArtifactModel | None = None
    onchain: OnchainPublicationModel | None = None
    challenge: ChallengeModel | None = None
    validation: ValidationTrailModel | None = None
    reputation_trail: ReputationTrailModel | None = None


class AuditListResponse(BaseModel):
    items: list[AuditRecordModel]


class TargetAuditClaimsResponse(BaseModel):
    target_contract: str
    target_key: str
    items: list[AuditRecordModel]


class TargetComparisonSummaryModel(BaseModel):
    claim_count: int
    published_count: int
    challenged_count: int
    resolved_count: int
    max_severity: int


class AuditorReputationModel(BaseModel):
    score: int
    band: Literal["provisional", "trusted", "mixed", "contested"]
    resolved_challenge_count: int
    challenge_rejected_count: int
    challenge_upheld_count: int
    open_challenge_count: int
    published_claim_count: int
    draft_claim_count: int
    last_resolved_at: str | None = None
    source: str | None = None
    registry_address: str | None = None
    agent_id: int | None = None
    total_stake_wei: int | None = None
    last_update: int | None = None
    formula: str


class AuditorReputationResponse(BaseModel):
    service_id: str
    reputation: AuditorReputationModel


class TargetComparisonResponse(BaseModel):
    target_contract: str
    target_key: str
    summary: TargetComparisonSummaryModel
    items: list[AuditRecordModel]


class MarketplacePreviewFiltersModel(BaseModel):
    minimum_stake_wei: int = 0
    whitelist_mode: Literal["open", "allowlist"] = "open"
    allowed_service_ids: list[str] = Field(default_factory=list)
    required_identity_service_id: str | None = None
    required_identity_agent_id: int | None = None
    required_identity_registry: str | None = None


class MarketplacePreviewRequest(BaseModel):
    contract_address: str | None = None
    bounty_wei: int = 0
    protocol_fee_wei: int = 0
    filters: MarketplacePreviewFiltersModel = Field(
        default_factory=MarketplacePreviewFiltersModel
    )


class MarketplacePreviewChainContextModel(BaseModel):
    authority: Literal["chain_authoritative"] = "chain_authoritative"
    network: str
    chain_id: int
    required_stake_wei: int
    challenge_window_seconds: int


class MarketplacePreviewCostBreakdownModel(BaseModel):
    authority: Literal["api_preview"] = "api_preview"
    bounty_wei: int
    protocol_fee_wei: int
    total_wei: int


class MarketplacePreviewAuditorEligibilityModel(BaseModel):
    matches: bool
    approximate: bool = True
    reasons: list[str] = Field(default_factory=list)


class MarketplacePreviewAuditorMatchModel(BaseModel):
    service_id: str
    name: str
    agent_id: int | None = None
    agent_registry: str | None = None
    reputation: AuditorReputationModel | None = None
    stake_preview_wei: int | None = None
    eligibility: MarketplacePreviewAuditorEligibilityModel


class MarketplacePreviewEligibilitySummaryModel(BaseModel):
    authority: Literal["api_preview"] = "api_preview"
    total_auditors: int
    eligible_auditors: int
    approximate: bool = True


class MarketplacePreviewResponse(BaseModel):
    target_contract: str | None = None
    request_state: Literal["preview_only"] = "preview_only"
    chain_context: MarketplacePreviewChainContextModel
    cost_breakdown: MarketplacePreviewCostBreakdownModel
    filters: MarketplacePreviewFiltersModel
    eligibility_summary: MarketplacePreviewEligibilitySummaryModel
    auditor_matches: list[MarketplacePreviewAuditorMatchModel]
    preview_disclaimer: str


class AuditRequestRecordModel(BaseModel):
    request_id: str
    status: str
    requester: str | None = None
    input_kind: Literal["deployed_address", "source_bundle", "repository_url"] = (
        "deployed_address"
    )
    contract_address: str
    chain_id: int | None = None
    entry_contract: str | None = None
    bounty_wei: int
    protocol_fee_wei: int = 0
    response_window_seconds: int | None = None
    response_window_end: str | None = None
    created_at: str | None = None
    claim_count: int = 0
    request_tx_hash: str | None = None
    request_tx_url: str | None = None
    filters: MarketplacePreviewFiltersModel = Field(
        default_factory=MarketplacePreviewFiltersModel
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditRequestListResponse(BaseModel):
    items: list[AuditRequestRecordModel]


class AuditRequestEligibilityResponse(BaseModel):
    request_id: str
    auditor_service_id: str
    eligible: bool
    approximate: bool = True
    minimum_stake_wei: int = 0
    reasons: list[str] = Field(default_factory=list)


class AuditRequestClaimModel(BaseModel):
    claim_id: str
    request_id: str
    audit_id: str
    claim_state: str
    auditor_service_id: str
    agent_id: int | None = None
    agent_registry: str | None = None
    auditor_address: str | None = None
    stake_wei: int
    submitted_at: str | None = None
    report_hash: str
    metadata_hash: str
    max_severity: int
    finding_count: int
    tx_hash: str | None = None
    tx_url: str | None = None
    status: str
    target_contract: str
    challenge_policy: ChallengePolicyModel | None = None


class AuditRequestClaimListResponse(BaseModel):
    items: list[AuditRequestClaimModel]


class CreateAuditMarketplaceRequest(BaseModel):
    contract_address: str
    bounty_wei: int = Field(..., gt=0)
    response_window_seconds: int = Field(..., gt=0)
    filters: MarketplacePreviewFiltersModel = Field(
        default_factory=MarketplacePreviewFiltersModel
    )


class SubmitAuditRequestClaimRequest(BaseModel):
    audit_id: str
    stake_wei: int = Field(..., ge=0)
    challenge_policy: ChallengePolicyModel = Field(default_factory=ChallengePolicyModel)


ChallengerEventKind = Literal[
    "audit_published",
    "challenge_opened",
    "challenge_resolved",
]


class ChallengerFeedItemModel(BaseModel):
    event_id: str
    event_kind: ChallengerEventKind
    event_timestamp: str
    audit_id: str
    published_audit_id: int | None = None
    service_id: str
    auditor_id: str
    auditor_name: str
    target_contract: str
    target_key: str
    publish_timestamp: str | None = None
    challenge_window_end: str | None = None
    current_state: str
    report_hash: str
    metadata_hash: str
    summary: str
    max_severity: int
    finding_count: int
    publish_tx_hash: str | None = None
    publish_tx_url: str | None = None
    challenge_tx_hash: str | None = None
    challenge_tx_url: str | None = None
    verification_status: str | None = None
    verification_dossier_path: str | None = None
    resolve_tx_hash: str | None = None
    resolve_tx_url: str | None = None
    resolution: str | None = None


class ChallengerFeedResponse(BaseModel):
    items: list[ChallengerFeedItemModel]


class DemoFixtureModel(BaseModel):
    id: str
    label: str
    contract_name: str
    entry_contract: str
    benchmark_id: str
    address: str
    challenge_proof_uri: str
    note: str
    source_path: str


class DemoFixtureListResponse(BaseModel):
    items: list[DemoFixtureModel]


class HealthResponse(BaseModel):
    status: str


class PublicContractConfigResponse(BaseModel):
    network: str
    chain_id: int
    contract_address: str | None = None
    explorer_base_url: str
    arbiter: str | None = None
    auditor: AuditorProfileModel
    auditor_service: AuditorServiceRecordModel
    required_stake_wei: int
    required_challenge_bond_wei: int
    challenge_window_seconds: int
    deployment_ready: bool


class SourceBundleUploadResponse(BaseModel):
    original_filename: str
    source_bundle_uri: str
    storage_backend: str = "local"
    source_bundle_label: str | None = None
    entry_contract: str | None = None


class SourceBundleUploadRequest(BaseModel):
    filename: str
    content_base64: str

    @model_validator(mode="after")
    def validate_base64(self) -> "SourceBundleUploadRequest":
        try:
            base64.b64decode(self.content_base64, validate=True)
        except ValueError as exc:
            raise ValueError("content_base64 must be valid base64 data") from exc
        return self


InputKind = Literal["deployed_address", "demo_fixture", "source_bundle", "repository_url"]


class AuditSubmissionModel(BaseModel):
    input_kind: InputKind
    service_id: str | None = None
    chain_id: int | None = None
    contract_address: str | None = None
    fixture_id: str | None = None
    entry_contract: str | None = None
    source_bundle_uri: str | None = None
    source_bundle_label: str | None = None
    repository_url: str | None = None


class CreateAuditRequest(AuditSubmissionModel):
    input_kind: InputKind = "deployed_address"
    submitted_by: str = "anonymous"

    @model_validator(mode="after")
    def validate_submission_requirements(self) -> "CreateAuditRequest":
        if self.input_kind == "deployed_address" and not self.contract_address:
            raise ValueError("contract_address is required for deployed_address submissions")
        if self.input_kind == "demo_fixture" and not self.fixture_id:
            raise ValueError("fixture_id is required for demo_fixture submissions")
        if self.input_kind == "source_bundle" and not self.source_bundle_uri:
            raise ValueError("source_bundle_uri is required for source_bundle submissions")
        if self.input_kind == "repository_url" and not self.repository_url:
            raise ValueError("repository_url is required for repository_url submissions")
        return self


class PublishAuditRequest(BaseModel):
    stake_wei: int = Field(default=10_000_000_000_000_000, ge=0)
    agent_identity: str | None = None
    challenge_policy: ChallengePolicyModel = Field(default_factory=ChallengePolicyModel)


EvidenceType = Literal["deterministic_fixture", "executable_test"]
ExecutionEnv = Literal["foundry"]


class ExecutableEvidenceManifestModel(BaseModel):
    bundle_format: Literal["proof-of-audit-executable-evidence/v1"]
    execution_env: ExecutionEnv
    entrypoint: str
    target_chain_id: int
    test_contract: str | None = None
    match_contract: str | None = None
    pinned_block_number: int | None = None
    expected_file_hashes: dict[str, str] = Field(default_factory=dict)
    metadata_path: str | None = None

    @model_validator(mode="after")
    def validate_selector_fields(self) -> "ExecutableEvidenceManifestModel":
        if self.test_contract and self.match_contract:
            raise ValueError("test_contract and match_contract are mutually exclusive")
        return self


class ChallengeAuditRequest(BaseModel):
    proof_uri: str
    evidence_type: EvidenceType = "deterministic_fixture"
    execution_env: ExecutionEnv | None = None
    evidence_manifest: ExecutableEvidenceManifestModel | None = None
    challenger: str = "anonymous-challenger"

    @model_validator(mode="after")
    def validate_challenge_payload(self) -> "ChallengeAuditRequest":
        if self.evidence_manifest is not None and self.execution_env is None:
            self.execution_env = self.evidence_manifest.execution_env
        if self.evidence_type == "executable_test" and self.execution_env is None:
            self.execution_env = "foundry"
        if self.evidence_type == "deterministic_fixture" and self.execution_env is not None:
            raise ValueError(
                "execution_env is only supported for executable_test challenge evidence"
            )
        if self.evidence_type == "deterministic_fixture" and self.evidence_manifest is not None:
            raise ValueError(
                "evidence_manifest is only supported for executable_test challenge evidence"
            )
        if (
            self.evidence_manifest is not None
            and self.execution_env is not None
            and self.evidence_manifest.execution_env != self.execution_env
        ):
            raise ValueError(
                "evidence_manifest.execution_env must match execution_env when both are provided"
            )
        return self


class ResolveAuditRequest(BaseModel):
    upheld: bool
    resolved_by: str = "arbiter"


class ErrorResponse(BaseModel):
    error: str
    message: str | None = None
    field: str | None = None
    detail: Any | None = None
