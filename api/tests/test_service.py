import tempfile
import unittest
from pathlib import Path

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.service import AuditService


class AuditServiceTest(unittest.TestCase):
    def test_list_audits_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir))
            first = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="first",
            )
            second = service.create_audit(
                "0x1000000000000000000000000000000000000002",
                submitted_by="second",
            )

            listed = service.list_audits()

            self.assertEqual(listed[0]["id"], second["id"])
            self.assertEqual(listed[1]["id"], first["id"])

    def test_create_publish_and_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(
                Path(tmpdir),
                contract_config=ContractConfig.from_env(
                    {"PROOF_OF_AUDIT_CONTRACT_ADDRESS": "0xfeedface"}
                ),
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="judge",
            )

            self.assertEqual(created["status"], "draft")
            self.assertEqual(created["report"]["benchmark_id"], "reentrancy-bank")

            published = service.publish_audit(created["id"], 10**16, "auditor-agent-v1")
            self.assertEqual(published["status"], "published")
            self.assertEqual(published["onchain"]["network"], "base-sepolia")
            self.assertEqual(published["onchain"]["chain_id"], 84532)
            self.assertEqual(
                published["onchain"]["contract_address"], "0xfeedface"
            )
            self.assertTrue(
                published["onchain"]["publish_tx_url"].startswith(
                    "https://sepolia.basescan.org/tx/0x"
                )
            )

            challenged = service.challenge_audit(
                created["id"],
                "ipfs://demo-poc",
                challenger="whitehat",
            )
            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(challenged["challenge"]["status"], "accepted")
            self.assertTrue(
                challenged["challenge"]["challenge_tx_url"].startswith(
                    "https://sepolia.basescan.org/tx/0x"
                )
            )

    def test_challenge_requires_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir))
            created = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="judge",
            )

            with self.assertRaisesRegex(
                ValueError, "audit must be published before challenge"
            ):
                service.challenge_audit(
                    created["id"],
                    "ipfs://demo-poc",
                    challenger="whitehat",
                )


if __name__ == "__main__":
    unittest.main()
