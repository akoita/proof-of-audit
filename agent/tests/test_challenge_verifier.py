from proof_of_audit_agent.challenge_verifier import (
    EvidenceContext,
    ProofUriChallengeVerifier,
)


def _context(proof_uri: str) -> EvidenceContext:
    return EvidenceContext(
        proof_uri=proof_uri,
        benchmark_id="clean-vault",
        target_contract="0x1000000000000000000000000000000000000001",
        published_report={},
    )


def test_plain_proof_uri_challenges_require_manual_review() -> None:
    verifier = ProofUriChallengeVerifier()

    result = verifier.verify(_context("ipfs://challenge-evidence"))

    assert result.status == "verifier_unavailable"
    assert result.resolution is None
    assert result.upheld is None


def test_blank_proof_uri_is_invalid_evidence() -> None:
    verifier = ProofUriChallengeVerifier()

    result = verifier.verify(_context("   "))

    assert result.status == "invalid_evidence"
    assert result.resolution is None
