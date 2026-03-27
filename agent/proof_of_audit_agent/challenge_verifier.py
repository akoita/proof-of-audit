from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

VERIFIER_NAME = "manual-proof-review-v1"
CHALLENGE_CLAIM_SCHEMA_VERSION = "challenge-claim/v1"
NORMALIZED_FINDING_SCHEMA_VERSION = "normalized-audit-finding/v1"
VERIFICATION_DOSSIER_SCHEMA_VERSION = "challenge-verifier-dossier/v1"


@dataclass(frozen=True)
class EvidenceContext:
    proof_uri: str
    benchmark_id: str | None
    target_contract: str
    published_report: dict[str, Any]
    evidence_type: str = "deterministic_fixture"
    execution_env: str | None = None
    evidence_manifest: dict[str, Any] | None = None
    chain_id: int | None = None
    rpc_url: str | None = None
    snapshot_block_number: int | None = None
    committed_evidence_hash: str | None = None


class ChallengeVerifierStrategy(Protocol):
    def verify(self, context: EvidenceContext) -> "ChallengeVerificationResult":
        ...


@dataclass(frozen=True)
class StructuredChallengeClaim:
    claim_type: str
    basis: str
    confidence: str = "unknown"
    affected_surfaces: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    demonstrated_effect: str | None = None
    claimed_impact: str | None = None
    supporting_signals: list[str] = field(default_factory=list)
    schema_version: str = CHALLENGE_CLAIM_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "claim_type": self.claim_type,
            "basis": self.basis,
            "confidence": self.confidence,
            "affected_surfaces": list(self.affected_surfaces),
            "preconditions": list(self.preconditions),
            "demonstrated_effect": self.demonstrated_effect,
            "claimed_impact": self.claimed_impact,
            "supporting_signals": list(self.supporting_signals),
        }


@dataclass(frozen=True)
class VerificationFindingMatch:
    finding_id: str
    relationship: str
    confidence: str = "unknown"
    rationale: str | None = None
    score: float | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "relationship": self.relationship,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "score": self.score,
        }


@dataclass(frozen=True)
class VerificationDossier:
    verifier_version: str
    evidence_type: str
    integrity_status: str
    execution_status: str
    comparison_status: str
    policy_status: str
    advisory_only: bool
    challenge_claim: StructuredChallengeClaim | None = None
    matched_finding_ids: list[str] = field(default_factory=list)
    matched_findings: list[VerificationFindingMatch] = field(default_factory=list)
    unmatched_signals: list[str] = field(default_factory=list)
    comparison_confidence: str = "unknown"
    comparison_rationale: str | None = None
    disagreement_status: str = "not_checked"
    disagreement_detail: str | None = None
    committed_evidence_hash: str | None = None
    execution_env: str | None = None
    backend: str | None = None
    isolation_level: str | None = None
    source_path: str | None = None
    fork_block_number: int | None = None
    recommended_resolution: str | None = None
    abstained: bool = False
    policy_confidence: str = "unknown"
    policy_rationale: str | None = None
    model_metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = VERIFICATION_DOSSIER_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "verifier_version": self.verifier_version,
            "evidence_type": self.evidence_type,
            "integrity": {
                "status": self.integrity_status,
                "committed_evidence_hash": self.committed_evidence_hash,
            },
            "execution": {
                "status": self.execution_status,
                "execution_env": self.execution_env,
                "backend": self.backend,
                "isolation_level": self.isolation_level,
                "source_path": self.source_path,
                "fork_block_number": self.fork_block_number,
            },
            "claim": (
                self.challenge_claim.to_payload()
                if self.challenge_claim is not None
                else None
            ),
            "comparison": {
                "status": self.comparison_status,
                "confidence": self.comparison_confidence,
                "rationale": self.comparison_rationale,
                "matched_finding_ids": list(self.matched_finding_ids),
                "matched_findings": [
                    finding.to_payload() for finding in self.matched_findings
                ],
                "unmatched_signals": list(self.unmatched_signals),
                "disagreement_status": self.disagreement_status,
                "disagreement_detail": self.disagreement_detail,
            },
            "policy": {
                "status": self.policy_status,
                "advisory_only": self.advisory_only,
                "recommended_resolution": self.recommended_resolution,
                "abstained": self.abstained,
                "confidence": self.policy_confidence,
                "rationale": self.policy_rationale,
            },
            "model_metadata": dict(self.model_metadata),
        }


@dataclass(frozen=True)
class ChallengeVerificationResult:
    verifier: str
    status: str
    summary: str
    detail: str
    case_id: str | None = None
    resolution: str | None = None
    advisory_only: bool = False
    execution_log: str | None = None
    matched_findings: list[str] = field(default_factory=list)
    unmatched_findings: list[str] = field(default_factory=list)
    challenge_claim: StructuredChallengeClaim | None = None
    verification_dossier: VerificationDossier | None = None

    @property
    def upheld(self) -> bool | None:
        if self.resolution == "upheld":
            return True
        if self.resolution == "rejected":
            return False
        return None


class ProofUriChallengeVerifier:
    """Generic proof-URI verifier that always routes plain evidence to manual review."""

    def verify(
        self,
        context: EvidenceContext | str,
        proof_uri: str | None = None,
    ) -> ChallengeVerificationResult:
        if isinstance(context, EvidenceContext):
            proof_uri = context.proof_uri
        else:
            proof_uri = proof_uri or ""

        normalized_proof_uri = proof_uri.strip()
        if not normalized_proof_uri:
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="invalid_evidence",
                summary="Challenge evidence must include a proof URI.",
                detail="Submit a non-empty proof_uri so the challenge record can point reviewers to the supplied evidence.",
                challenge_claim=StructuredChallengeClaim(
                    claim_type="external_proof_reference",
                    basis="plain-proof-uri",
                    demonstrated_effect="No proof URI was supplied, so the claim could not be evaluated.",
                    confidence="low",
                ),
                verification_dossier=VerificationDossier(
                    verifier_version=VERIFIER_NAME,
                    evidence_type=(
                        context.evidence_type
                        if isinstance(context, EvidenceContext)
                        else "deterministic_fixture"
                    ),
                    integrity_status="invalid",
                    execution_status="not_executed",
                    comparison_status="not_assessed",
                    policy_status="manual_review_required",
                    advisory_only=False,
                    challenge_claim=StructuredChallengeClaim(
                        claim_type="external_proof_reference",
                        basis="plain-proof-uri",
                        demonstrated_effect="No proof URI was supplied, so the claim could not be evaluated.",
                        confidence="low",
                    ),
                    recommended_resolution="manual_review_required",
                    abstained=True,
                ),
            )

        claim = StructuredChallengeClaim(
            claim_type="external_proof_reference",
            basis="plain-proof-uri",
            demonstrated_effect="A reviewer should inspect the submitted proof URI and determine whether it contradicts the published audit.",
            claimed_impact="Manual reviewers must inspect the linked evidence.",
            confidence="unknown",
        )
        return ChallengeVerificationResult(
            verifier=VERIFIER_NAME,
            status="verifier_unavailable",
            summary="Plain proof-URI challenges require manual review.",
            detail="The deterministic benchmark verifier has been retired. Non-executable challenge evidence is now recorded for manual evaluation rather than auto-resolved from a curated lookup table.",
            challenge_claim=claim,
            verification_dossier=VerificationDossier(
                verifier_version=VERIFIER_NAME,
                evidence_type=(
                    context.evidence_type
                    if isinstance(context, EvidenceContext)
                    else "deterministic_fixture"
                ),
                integrity_status="valid",
                execution_status="not_executed",
                comparison_status="not_assessed",
                policy_status="manual_review_required",
                advisory_only=False,
                challenge_claim=claim,
                committed_evidence_hash=(
                    context.committed_evidence_hash
                    if isinstance(context, EvidenceContext)
                    else None
                ),
                recommended_resolution="manual_review_required",
                abstained=True,
            ),
        )

    def suggested_proof_uri(self, benchmark_id: str) -> str:
        _ = benchmark_id
        return "ipfs://challenge-evidence"
