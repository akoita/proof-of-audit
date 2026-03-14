import unittest
import json
from pathlib import Path
import tempfile

from proof_of_audit_api.config import ContractConfig, load_env_file

def load_base_sepolia_manifest() -> dict[str, object]:
    return json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "deployments"
            / "base-sepolia.json"
        ).read_text(encoding="utf-8")
    )


class ContractConfigTest(unittest.TestCase):
    def test_defaults_match_base_sepolia_profile(self) -> None:
        manifest = load_base_sepolia_manifest()
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
        self.assertEqual(
            config.auditor_service.registration_uri,
            "https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json",
        )
        self.assertEqual(
            config.auditor_service.agent_id,
            manifest["auditor_identity"]["agent_id"],
        )
        self.assertEqual(
            config.auditor_service.agent_registry,
            manifest["auditor_identity"]["registry_address"],
        )
        self.assertEqual(
            config.auditor_service.identity_source,
            manifest["auditor_identity"]["source"],
        )
        self.assertEqual(config.auditor_service.discovery_path, "/auditor")
        self.assertEqual(config.auditor_service.submit_path, "/audits")
        self.assertEqual(
            config.auditor_service.validation_registry_address,
            str(manifest["validation_bridge"]["registry_address"]),
        )
        self.assertEqual(config.auditor_service.validation_source, "erc8004-official")
        self.assertEqual(
            config.auditor_service.validation_request_path_template,
            "/audits/{id}/validation/request",
        )
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
                "PROOF_OF_AUDIT_PRIVATE_KEY": "0x59c6995e998f97a5a0044966f094538e5d8f7c6f8b3631d8c0eb1f68d6f6c7e6",
                "PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY": "0x8b3a350cf5c34c9194ca3a545d0f15e3b8f1f0d0c2e5b2f5d7a9a1f6715f89fd",
                "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY": "0x0dbbe8ebf7d0313f4fd5401397cbe8bb8d65b1b845a70d820ee7da8db36805b4",
                "PROOF_OF_AUDIT_DEMO_FIXTURES_FILE": "/tmp/demo-fixtures.json",
                "PROOF_OF_AUDIT_REQUIRED_STAKE_WEI": "123",
                "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI": "45",
                "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS": "67",
                "PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS": "0xdef",
                "PROOF_OF_AUDIT_VALIDATION_BRIDGE_SOURCE": "project-local-custom",
                "PROOF_OF_AUDIT_RUNTIME_API_URL": "http://127.0.0.1:9999",
            }
        )

        self.assertEqual(config.contract_address, "0xabc")
        self.assertEqual(config.arbiter, "0xarbiter")
        self.assertEqual(config.rpc_url, "https://rpc.example")
        self.assertEqual(
            config.publisher_private_key,
            "0x59c6995e998f97a5a0044966f094538e5d8f7c6f8b3631d8c0eb1f68d6f6c7e6",
        )
        self.assertEqual(
            config.auditor_owner_private_key,
            "0x8b3a350cf5c34c9194ca3a545d0f15e3b8f1f0d0c2e5b2f5d7a9a1f6715f89fd",
        )
        self.assertEqual(
            config.validator_private_key,
            "0x0dbbe8ebf7d0313f4fd5401397cbe8bb8d65b1b845a70d820ee7da8db36805b4",
        )
        self.assertIsNone(config.demo_fixtures_file)
        self.assertEqual(config.required_stake_wei, 123)
        self.assertEqual(config.required_challenge_bond_wei, 45)
        self.assertEqual(config.challenge_window_seconds, 67)
        self.assertEqual(config.validation_registry_address, "0xdef")
        self.assertEqual(config.validation_bridge_source, "project-local-custom")
        self.assertEqual(config.runtime_api_base_url, "http://127.0.0.1:9999")
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
