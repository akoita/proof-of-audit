import unittest

from proof_of_audit_agent.challenge_verifier import DeterministicChallengeVerifier


class DeterministicChallengeVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = DeterministicChallengeVerifier()

    def test_clean_vault_poc_is_verified_and_upheld(self) -> None:
        result = self.verifier.verify(
            "clean-vault",
            "ipfs://clean-vault/missed-reentrancy",
        )

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.resolution, "upheld")
        self.assertTrue(result.upheld)

    def test_reported_finding_poc_is_verified_and_rejected(self) -> None:
        result = self.verifier.verify(
            "reentrancy-bank",
            "ipfs://reentrancy-bank/withdraw-drain",
        )

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.resolution, "rejected")
        self.assertFalse(result.upheld)

    def test_unexpected_poc_is_invalid_evidence(self) -> None:
        result = self.verifier.verify(
            "clean-vault",
            "ipfs://wrong-proof",
        )

        self.assertEqual(result.status, "invalid_evidence")
        self.assertIsNone(result.resolution)

    def test_unknown_benchmark_requires_manual_review(self) -> None:
        result = self.verifier.verify(
            "unknown",
            "ipfs://benchmark-proof",
        )

        self.assertEqual(result.status, "verifier_unavailable")
        self.assertIsNone(result.resolution)


if __name__ == "__main__":
    unittest.main()
