from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FindingModel(BaseModel):
    title: str
    severity: str
    description: str
    recommendation: str
    detector: str


class AuditReportModel(BaseModel):
    benchmark_id: str
    contract_address: str
    summary: str
    findings: list[FindingModel]
    supported_checks: list[str]
    confidence: str
    report_hash: str
    metadata_hash: str
    max_severity: int


class OnchainPublicationModel(BaseModel):
    network: str
    agent_identity: str
    stake_wei: int
    report_hash: str
    metadata_hash: str
    max_severity: int
    finding_count: int
    publish_tx_hash: str


class ChallengeModel(BaseModel):
    challenger: str
    proof_uri: str
    submitted_at: str
    verifier: str
    status: str
    challenge_tx_hash: str


class AuditRecordModel(BaseModel):
    id: str
    contract_address: str
    submitted_by: str
    status: str
    created_at: str
    report: AuditReportModel
    onchain: OnchainPublicationModel | None = None
    challenge: ChallengeModel | None = None


class AuditListResponse(BaseModel):
    items: list[AuditRecordModel]


class HealthResponse(BaseModel):
    status: str


class CreateAuditRequest(BaseModel):
    contract_address: str
    submitted_by: str = "anonymous"


class PublishAuditRequest(BaseModel):
    stake_wei: int = Field(default=10_000_000_000_000_000, ge=0)
    agent_identity: str = "auditor-agent-v1"


class ChallengeAuditRequest(BaseModel):
    proof_uri: str
    challenger: str = "anonymous-challenger"


class ErrorResponse(BaseModel):
    error: str
    message: str | None = None
    field: str | None = None
    detail: Any | None = None
