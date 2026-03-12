from proof_of_audit_agent.challenge_verifier import DeterministicChallengeVerifier


def test_clean_vault_poc_is_verified_and_upheld() -> None:
    verifier = DeterministicChallengeVerifier()

    result = verifier.verify(
        "clean-vault",
        "ipfs://clean-vault/missed-reentrancy",
    )

    assert result.status == "verified"
    assert result.resolution == "upheld"
    assert result.upheld is True


def test_reported_finding_poc_is_verified_and_rejected() -> None:
    verifier = DeterministicChallengeVerifier()

    result = verifier.verify(
        "reentrancy-bank",
        "ipfs://reentrancy-bank/withdraw-drain",
    )

    assert result.status == "verified"
    assert result.resolution == "rejected"
    assert result.upheld is False


def test_multi_finding_vault_poc_is_verified_and_rejected() -> None:
    verifier = DeterministicChallengeVerifier()

    result = verifier.verify(
        "dual-risk-vault",
        "ipfs://dual-risk-vault/owner-takeover",
    )

    assert result.status == "verified"
    assert result.resolution == "rejected"


def test_unexpected_poc_is_invalid_evidence() -> None:
    verifier = DeterministicChallengeVerifier()

    result = verifier.verify(
        "clean-vault",
        "ipfs://wrong-proof",
    )

    assert result.status == "invalid_evidence"
    assert result.resolution is None


def test_unknown_benchmark_requires_manual_review() -> None:
    verifier = DeterministicChallengeVerifier()

    result = verifier.verify(
        "unknown",
        "ipfs://benchmark-proof",
    )

    assert result.status == "verifier_unavailable"
    assert result.resolution is None
