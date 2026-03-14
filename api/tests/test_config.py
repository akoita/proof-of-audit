import unittest
from pathlib import Path
import tempfile

from proof_of_audit_api.config import ContractConfig, load_env_file


class ContractConfigTest(unittest.TestCase):
    def test_defaults_match_base_sepolia_profile(self) -> None:
        config = ContractConfig.from_env({})

        self.assertEqual(config.network, "base-sepolia")
        self.assertEqual(config.chain_id, 84532)
        self.assertEqual(config.explorer_base_url, "https://sepolia.basescan.org")
        self.assertEqual(config.required_stake_wei, 10**16)
        self.assertEqual(config.required_challenge_bond_wei, 5 * 10**15)
        self.assertEqual(config.challenge_window_seconds, 86400)
        self.assertEqual(
            config.auditor.manifest_schema,
            "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        )
        self.assertEqual(
            config.auditor_service.registration_kind,
            "offchain_manifest",
        )
        self.assertEqual(
            config.auditor_service.registration_type,
            "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        )
        self.assertEqual(config.auditor_service.discovery_path, "/auditor")
        self.assertEqual(config.auditor_service.submit_path, "/audits")
        self.assertTrue(config.auditor_service.manifest_hash)
        self.assertFalse(config.deployment_ready)

    def test_reads_environment_overrides(self) -> None:
        config = ContractConfig.from_env(
            {
                "PROOF_OF_AUDIT_NETWORK": "base-sepolia",
                "PROOF_OF_AUDIT_CHAIN_ID": "84532",
                "PROOF_OF_AUDIT_CONTRACT_ADDRESS": "0xabc",
                "PROOF_OF_AUDIT_EXPLORER_BASE_URL": "https://sepolia.basescan.org/",
                "PROOF_OF_AUDIT_ARBITER": "0xarbiter",
                "PROOF_OF_AUDIT_RPC_URL": "https://rpc.example",
                "PROOF_OF_AUDIT_PRIVATE_KEY": "secret",
                "PROOF_OF_AUDIT_DEMO_FIXTURES_FILE": "/tmp/demo-fixtures.json",
                "PROOF_OF_AUDIT_REQUIRED_STAKE_WEI": "123",
                "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI": "45",
                "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS": "67",
            }
        )

        self.assertEqual(config.contract_address, "0xabc")
        self.assertEqual(config.arbiter, "0xarbiter")
        self.assertEqual(config.rpc_url, "https://rpc.example")
        self.assertEqual(config.publisher_private_key, "secret")
        self.assertIsNone(config.demo_fixtures_file)
        self.assertEqual(config.required_stake_wei, 123)
        self.assertEqual(config.required_challenge_bond_wei, 45)
        self.assertEqual(config.challenge_window_seconds, 67)
        self.assertTrue(config.deployment_ready)
        self.assertEqual(
            config.transaction_url("0x123"),
            "https://sepolia.basescan.org/tx/0x123",
        )

    def test_reads_env_file_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.local"
            env_file.write_text(
                "\n".join(
                    [
                        "PROOF_OF_AUDIT_NETWORK=anvil-local",
                        "PROOF_OF_AUDIT_CHAIN_ID=31337",
                        "PROOF_OF_AUDIT_CONTRACT_ADDRESS=0xlocal",
                        "PROOF_OF_AUDIT_RPC_URL=http://127.0.0.1:8545",
                        f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={tmpdir}/fixtures.json",
                    ]
                ),
                encoding="utf-8",
            )
            fixtures_file = Path(tmpdir) / "fixtures.json"
            fixtures_file.write_text('{"fixtures":[]}\n', encoding="utf-8")

            self.assertEqual(
                load_env_file(env_file)["PROOF_OF_AUDIT_NETWORK"], "anvil-local"
            )
            config = ContractConfig.from_env(env_file=env_file)

            self.assertEqual(config.network, "anvil-local")
            self.assertEqual(config.chain_id, 31337)
            self.assertEqual(config.contract_address, "0xlocal")
            self.assertEqual(config.rpc_url, "http://127.0.0.1:8545")
            self.assertEqual(config.demo_fixtures_file, fixtures_file)
            self.assertTrue(config.deployment_ready)
