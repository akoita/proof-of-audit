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
        self.assertEqual(
            config.auditor_service.submission_modes,
            ("demo_fixture", "deployed_address", "source_bundle", "repository_url"),
        )
        self.assertEqual(
            config.auditor_service.resolution_modes,
            ("deterministic", "manual_fallback"),
        )
        self.assertTrue(config.auditor_service.deterministic_resolution_supported)
        self.assertTrue(config.auditor_service.manual_fallback_supported)
        self.assertTrue(config.auditor_service.manifest_hash)
        self.assertEqual(len(config.auditor_services), 1)
        self.assertEqual(
            config.auditor_services[0].service_id,
            config.auditor_service.service_id,
        )
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
                "PROOF_OF_AUDIT_WORKER_RUNTIME_MODE": "hybrid",
                "PROOF_OF_AUDIT_AGENT_FORGE_COMMAND": "/tmp/agent-forge",
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
        self.assertEqual(config.worker_runtime_mode, "hybrid")
        self.assertEqual(config.agent_forge_command, "/tmp/agent-forge")
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

    def test_loads_additional_auditors_from_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_file = Path(tmpdir) / "auditors.catalog.json"
            catalog_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "service": {
                                    "service_id": "external-auditor",
                                    "name": "External Auditor",
                                    "manifest_schema": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
                                    "manifest_hash": "deadbeef",
                                    "registration_kind": "offchain_manifest",
                                    "registration_type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
                                    "registration_endpoint": "/auditors/external-auditor/registration",
                                    "registration_uri": "https://example.invalid/external-auditor.json",
                                    "agent_id": 7,
                                    "agent_registry": "0x123",
                                    "identity_source": "erc8004-official",
                                    "capability": "audit_contract",
                                    "discovery_path": "/auditors/external-auditor",
                                    "submit_path": "/audits",
                                    "publish_path_template": "/audits/{id}/publish",
                                    "challenge_path_template": "/audits/{id}/challenge",
                                    "network": "base-sepolia",
                                    "active": True,
                                    "supported_trust": ["crypto-economic"],
                                    "registry_contract_address": "0x456",
                                    "validation_registry_address": "0x789",
                                    "validation_source": "erc8004-official",
                                    "validation_request_path_template": "/audits/{id}/validation/request",
                                    "validation_response_path_template": "/audits/{id}/validation/response",
                                    "submission_modes": ["deployed_address"],
                                    "resolution_modes": ["manual_fallback"],
                                    "deterministic_resolution_supported": False,
                                    "manual_fallback_supported": True,
                                },
                                "registration_document": {
                                    "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
                                    "name": "External Auditor",
                                    "description": "External auditor entry",
                                    "image": "https://example.invalid/external-auditor.png",
                                    "services": [
                                        {
                                            "name": "registration",
                                            "endpoint": "https://example.invalid/external-auditor.json",
                                        }
                                    ],
                                    "x402Support": False,
                                    "active": True,
                                    "registrations": [
                                        {
                                            "agentId": 7,
                                            "agentRegistry": "0x123",
                                        }
                                    ],
                                    "supportedTrust": ["crypto-economic"],
                                    "x-proof-of-audit": {
                                        "id": "external-auditor",
                                        "version": "1.0.0",
                                        "serviceType": "audit_contract",
                                        "capabilities": ["audit_contract"],
                                        "operator": "External",
                                        "resolutionPolicy": "manual",
                                    },
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            config = ContractConfig.from_env(
                {
                    "PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE": str(catalog_file),
                }
            )

            self.assertEqual(len(config.auditor_services), 2)
            self.assertEqual(
                config.auditor_services[1].service_id,
                "external-auditor",
            )
            self.assertIsNotNone(
                config.auditor_registration_document_by_service_id("external-auditor")
            )
