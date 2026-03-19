from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

VERIFIER_NAME = "manual-proof-review-v1"


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
    committed_evidence_hash: str | None = None


class ChallengeVerifierStrategy(Protocol):
    def verify(self, context: EvidenceContext) -> "ChallengeVerificationResult":
        ...


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
            )

        return ChallengeVerificationResult(
            verifier=VERIFIER_NAME,
            status="verifier_unavailable",
            summary="Plain proof-URI challenges require manual review.",
            detail="The deterministic benchmark verifier has been retired. Non-executable challenge evidence is now recorded for manual evaluation rather than auto-resolved from a curated lookup table.",
        )

    def suggested_proof_uri(self, benchmark_id: str) -> str:
        _ = benchmark_id
        return "ipfs://challenge-evidence"
