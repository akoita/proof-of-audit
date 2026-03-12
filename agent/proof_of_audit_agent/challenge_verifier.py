from __future__ import annotations

from dataclasses import dataclass

VERIFIER_NAME = "deterministic-benchmark-v1"


@dataclass(frozen=True)
class ChallengeCase:
    case_id: str
    benchmark_id: str
    expected_proof_uri: str
    resolution: str
    summary: str
    detail: str


@dataclass(frozen=True)
class ChallengeVerificationResult:
    verifier: str
    status: str
    summary: str
    detail: str
    case_id: str | None = None
    resolution: str | None = None

    @property
    def upheld(self) -> bool | None:
        if self.resolution == "upheld":
            return True
        if self.resolution == "rejected":
            return False
        return None


CHALLENGE_CASES = {
    "clean-vault": ChallengeCase(
        case_id="clean-vault-missed-reentrancy",
        benchmark_id="clean-vault",
        expected_proof_uri="ipfs://clean-vault/missed-reentrancy",
        resolution="upheld",
        summary="The submitted PoC demonstrates a missed issue against a contract marked clean.",
        detail="A successful Clean Vault regression challenge should slash the auditor because the draft report claimed no benchmark issue was present.",
    ),
    "reentrancy-bank": ChallengeCase(
        case_id="reentrancy-bank-confirmed-finding",
        benchmark_id="reentrancy-bank",
        expected_proof_uri="ipfs://reentrancy-bank/withdraw-drain",
        resolution="rejected",
        summary="The submitted PoC reproduces the same issue already reported by the audit.",
        detail="This challenge does not invalidate the attestation because the report already flagged the vulnerable withdraw path.",
    ),
    "admin-setter": ChallengeCase(
        case_id="admin-setter-confirmed-finding",
        benchmark_id="admin-setter",
        expected_proof_uri="ipfs://admin-setter/unauthorized-admin-change",
        resolution="rejected",
        summary="The submitted PoC confirms the existing access-control finding.",
        detail="A PoC that reproduces the missing access control issue validates the audit instead of disproving it.",
    ),
    "unchecked-treasury": ChallengeCase(
        case_id="unchecked-treasury-confirmed-finding",
        benchmark_id="unchecked-treasury",
        expected_proof_uri="ipfs://unchecked-treasury/unchecked-call-failure",
        resolution="rejected",
        summary="The submitted PoC confirms the unchecked external call already captured in the audit.",
        detail="The verifier rejects this challenge because the benchmark report already attested to the same failure mode.",
    ),
    "dual-risk-vault": ChallengeCase(
        case_id="dual-risk-vault-confirmed-finding",
        benchmark_id="dual-risk-vault",
        expected_proof_uri="ipfs://dual-risk-vault/owner-takeover",
        resolution="rejected",
        summary="The submitted PoC confirms one of the already reported benchmark findings in the multi-issue vault.",
        detail="The verifier rejects this challenge because the report already covers the unauthorized owner rotation in the Dual Risk Vault fixture.",
    ),
}


class DeterministicChallengeVerifier:
    """Evaluates benchmark PoC URIs against deterministic fixture expectations."""

    def verify(
        self,
        benchmark_id: str,
        proof_uri: str,
    ) -> ChallengeVerificationResult:
        challenge_case = CHALLENGE_CASES.get(benchmark_id)
        if challenge_case is None:
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="verifier_unavailable",
                summary="No deterministic verifier case is registered for this audit benchmark.",
                detail="Unknown or ad-hoc contracts require manual review because the benchmark verifier only supports curated demo fixtures.",
            )

        normalized_proof_uri = proof_uri.strip().lower()
        expected_proof_uri = challenge_case.expected_proof_uri.lower()

        if normalized_proof_uri != expected_proof_uri:
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="invalid_evidence",
                case_id=challenge_case.case_id,
                summary="The submitted PoC does not match the deterministic fixture artifact expected for this benchmark.",
                detail=f"Provide the curated artifact {challenge_case.expected_proof_uri} to reproduce the verifier outcome for {challenge_case.benchmark_id}.",
            )

        return ChallengeVerificationResult(
            verifier=VERIFIER_NAME,
            status="verified",
            case_id=challenge_case.case_id,
            resolution=challenge_case.resolution,
            summary=challenge_case.summary,
            detail=challenge_case.detail,
        )

    def suggested_proof_uri(self, benchmark_id: str) -> str:
        challenge_case = CHALLENGE_CASES.get(benchmark_id)
        if challenge_case is None:
            return "ipfs://benchmark-proof"
        return challenge_case.expected_proof_uri
