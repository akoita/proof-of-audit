import tempfile
import unittest
from pathlib import Path
import json

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.publisher import OnchainConfigurationError
from proof_of_audit_api.service import AuditService
from helpers import build_onchain_test_context


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
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
            )
            created = service.create_audit(
                onchain.web3.eth.accounts[2],
                submitted_by="judge",
            )

            self.assertEqual(created["status"], "draft")
            self.assertEqual(created["report"]["benchmark_id"], "unknown")

            published = service.publish_audit(created["id"], 10**16, "auditor-agent-v1")
            self.assertEqual(published["status"], "published")
            self.assertEqual(published["onchain"]["network"], "eth-tester")
            self.assertEqual(
                published["onchain"]["chain_id"], onchain.contract_config.chain_id
            )
            self.assertEqual(
                published["onchain"]["contract_address"],
                onchain.contract_config.contract_address,
            )
            self.assertTrue(
                published["onchain"]["publish_tx_url"].startswith(
                    "http://127.0.0.1:8545/tx/0x"
                )
            )
            self.assertEqual(published["onchain"]["audit_id"], 1)

            challenged = service.challenge_audit(
                created["id"],
                "ipfs://demo-poc",
                challenger="whitehat",
            )
            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(challenged["challenge"]["status"], "opened")
            self.assertEqual(
                challenged["challenge"]["challenger_address"],
                onchain.publisher.account.address,
            )
            self.assertEqual(
                challenged["challenge"]["challenge_bond_wei"],
                onchain.contract_config.required_challenge_bond_wei,
            )
            self.assertTrue(
                challenged["challenge"]["challenge_tx_url"].startswith(
                    "http://127.0.0.1:8545/tx/0x"
                )
            )
            audit_record = onchain.contract.functions.getAudit(1).call()
            self.assertEqual(int(audit_record[10]), 2)
            self.assertEqual(
                int(audit_record[7]),
                onchain.contract_config.required_challenge_bond_wei,
            )
            self.assertEqual(
                onchain.web3.to_checksum_address(audit_record[12]),
                onchain.publisher.account.address,
            )
            self.assertEqual(
                onchain.web3.to_hex(audit_record[13]),
                challenged["challenge"]["challenge_hash"],
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

    def test_duplicate_challenge_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
            )
            created = service.create_audit(
                onchain.web3.eth.accounts[2],
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")
            service.challenge_audit(
                created["id"],
                "ipfs://demo-poc",
                challenger="whitehat",
            )

            with self.assertRaisesRegex(ValueError, "already been challenged"):
                service.challenge_audit(
                    created["id"],
                    "ipfs://second-poc",
                    challenger="second-whitehat",
                )

    def test_publish_requires_onchain_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(
                Path(tmpdir),
                contract_config=ContractConfig.from_env({}),
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="judge",
            )

            with self.assertRaisesRegex(
                OnchainConfigurationError,
                "On-chain publishing is not configured",
            ):
                service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

    def test_lists_demo_fixtures_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixtures_file = Path(tmpdir) / "demo-fixtures.localhost.json"
            fixtures_file.write_text(
                json.dumps(
                    {
                        "fixtures": [
                            {
                                "id": "clean-vault",
                                "label": "Clean Vault",
                                "contract_name": "CleanVault",
                                "entry_contract": "CleanVault",
                                "benchmark_id": "clean-vault",
                                "address": "0x4444000000000000000000000000000000000004",
                                "note": "Clean benchmark with medium confidence",
                                "source_path": "demo/contracts/CleanVault.sol",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            service = AuditService(
                Path(tmpdir),
                contract_config=ContractConfig.from_env(
                    {"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE": str(fixtures_file)}
                ),
            )

            fixtures = service.list_demo_fixtures()

            self.assertEqual(len(fixtures), 1)
            self.assertEqual(fixtures[0]["label"], "Clean Vault")
            self.assertEqual(
                fixtures[0]["address"], "0x4444000000000000000000000000000000000004"
            )


if __name__ == "__main__":
    unittest.main()
