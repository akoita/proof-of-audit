import unittest
import json
from pathlib import Path
import tempfile

from proof_of_audit_api.config import (
    ContractConfig,
    address_from_private_key,
    load_env_file,
)

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
        self.assertIsNone(config.treasury_address)
        self.assertEqual(config.protocol_fee_bps, 0)
        self.assertEqual(config.resolution_fee_bps, 0)
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
        self.assertEqual(config.auditor_service.execution_mode, "local_worker")
        self.assertIsNone(config.auditor_service.execution_endpoint)
        self.assertEqual(
            config.auditor_service.settlement_mode,
            "native_proof_of_audit",
        )
        self.assertEqual(config.auditor_service.publication_mode, "api_mediated")
        self.assertEqual(
            config.auditor_service.staking_adapter_kind,
            "native_proof_of_audit",
        )
        self.assertIsNone(config.auditor_service.staking_adapter_address)
        self.assertEqual(config.auditor_service.staking_adapter_method, "publishAudit")
        self.assertEqual(
            config.auditor_service.publication_scope,
            "submit_selected_claim",
        )
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
            config.auditor_service.reputation_path_template,
            "/auditors/{id}/reputation",
        )
        self.assertEqual(
            config.auditor_service.submission_modes,
            ("demo_fixture", "deployed_address", "source_bundle", "repository_url"),
        )
        self.assertEqual(
            config.auditor_service.resolution_modes,
            ("advisory_verifier", "manual_fallback"),
        )
        self.assertFalse(config.auditor_service.deterministic_resolution_supported)
        self.assertTrue(config.auditor_service.manual_fallback_supported)
        self.assertTrue(config.auditor_service.manifest_hash)
        self.assertEqual(len(config.auditor_services), 1)
        self.assertEqual(
            config.auditor_services[0].service_id,
            config.auditor_service.service_id,
        )
        self.assertEqual(
            config.demo_fixtures_file,
            Path(__file__).resolve().parents[2]
            / "deployments"
            / "demo-fixtures.base-sepolia.json",
        )
        self.assertEqual(
            config.agent_forge_command,
            "python -m proof_of_audit_agent.agent_forge_cli",
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
                "PROOF_OF_AUDIT_TREASURY_ADDRESS": "0xtreasury",
                "PROOF_OF_AUDIT_PROTOCOL_FEE_BPS": "125",
                "PROOF_OF_AUDIT_RESOLUTION_FEE_BPS": "75",
                "PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS": "0xdef",
                "PROOF_OF_AUDIT_VALIDATION_BRIDGE_SOURCE": "project-local-custom",
                "PROOF_OF_AUDIT_REPUTATION_REGISTRY_ADDRESS": "0x987",
                "PROOF_OF_AUDIT_REPUTATION_BRIDGE_SOURCE": "project-local-custom",
                "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY": "0x5de4111a884cc4ff8f4b78a1810d7a2ec61b0ff7dd86e31ed5c8984f1a58dc6b",
                "PROOF_OF_AUDIT_RUNTIME_API_URL": "http://127.0.0.1:9999",
                "PROOF_OF_AUDIT_WORKER_RUNTIME_MODE": "hybrid",
                "PROOF_OF_AUDIT_AGENT_FORGE_COMMAND": "/tmp/agent-forge",
                "PROOF_OF_AUDIT_CHALLENGE_CLAIM_EXTRACTOR_COMMAND": "/tmp/challenge-claim-extractor",
                "PROOF_OF_AUDIT_CHALLENGE_CLAIM_EXTRACTOR_PROVIDER": "openai",
                "PROOF_OF_AUDIT_CHALLENGE_CLAIM_EXTRACTOR_MODEL": "gpt-5.4-mini",
                "PROOF_OF_AUDIT_CHALLENGE_CLAIM_EXTRACTOR_MIN_CONFIDENCE": "high",
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
        self.assertEqual(config.treasury_address, "0xtreasury")
        self.assertEqual(config.protocol_fee_bps, 125)
        self.assertEqual(config.resolution_fee_bps, 75)
        self.assertEqual(config.validation_registry_address, "0xdef")
        self.assertEqual(config.validation_bridge_source, "project-local-custom")
        self.assertEqual(config.reputation_registry_address, "0x987")
        self.assertEqual(config.reputation_bridge_source, "project-local-custom")
        self.assertEqual(
            config.reputation_operator_private_key,
            "0x5de4111a884cc4ff8f4b78a1810d7a2ec61b0ff7dd86e31ed5c8984f1a58dc6b",
        )
        self.assertEqual(config.runtime_api_base_url, "http://127.0.0.1:9999")
        self.assertEqual(config.worker_runtime_mode, "hybrid")
        self.assertEqual(config.agent_forge_command, "/tmp/agent-forge")
        self.assertIsNone(config.agent_forge_service_url)
        self.assertEqual(config.source_bundle_storage_kind, "local")
        self.assertEqual(
            config.challenge_claim_extractor_command,
            "/tmp/challenge-claim-extractor",
        )
        self.assertEqual(config.challenge_claim_extractor_provider, "openai")
        self.assertEqual(config.challenge_claim_extractor_model, "gpt-5.4-mini")
        self.assertEqual(config.challenge_claim_extractor_min_confidence, "high")
        self.assertTrue(config.deployment_ready)
        self.assertEqual(
            config.transaction_url("0x123"),
            "https://sepolia.basescan.org/tx/0x123",
        )

    def test_reads_hosted_agent_forge_service_settings(self) -> None:
        config = ContractConfig.from_env(
            {
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_URL": "https://agent-forge.example",
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_TOKEN": "token-123",
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_PROFILE_ID": "proof-of-audit-solidity-v2",
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_REPORT_SCHEMA": "proof-of-audit-report-v2",
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_POLL_INTERVAL_SECONDS": "0.5",
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_POLL_TIMEOUT_SECONDS": "120",
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_REQUEST_TIMEOUT_SECONDS": "15",
                "PROOF_OF_AUDIT_SOURCE_BUNDLE_STORAGE_KIND": "gcs",
                "PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_BUCKET": "proof-of-audit-source-bundles",
                "PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_PREFIX": "uploads/agent-forge",
            }
        )

        self.assertEqual(config.agent_forge_service_url, "https://agent-forge.example")
        self.assertEqual(config.agent_forge_service_token, "token-123")
        self.assertEqual(
            config.agent_forge_service_profile_id,
            "proof-of-audit-solidity-v2",
        )
        self.assertEqual(
            config.agent_forge_service_report_schema,
            "proof-of-audit-report-v2",
        )
        self.assertEqual(config.agent_forge_service_poll_interval_seconds, 0.5)
        self.assertEqual(config.agent_forge_service_poll_timeout_seconds, 120.0)
        self.assertEqual(config.agent_forge_service_request_timeout_seconds, 15.0)
        self.assertEqual(config.source_bundle_storage_kind, "gcs")
        self.assertEqual(
            config.source_bundle_gcs_bucket,
            "proof-of-audit-source-bundles",
        )
        self.assertEqual(
            config.source_bundle_gcs_prefix,
            "uploads/agent-forge",
        )

    def test_public_api_base_url_prefers_request_when_public_url_is_unset(self) -> None:
        config = ContractConfig.from_env(
            {
                "PROOF_OF_AUDIT_RUNTIME_API_URL": "http://127.0.0.1:8080",
            }
        )

        self.assertEqual(
            config.public_api_base_url("https://api.proof-of-audit.example.invalid/"),
            "https://api.proof-of-audit.example.invalid",
        )

    def test_public_api_base_url_uses_non_local_runtime_url(self) -> None:
        config = ContractConfig.from_env(
            {
                "PROOF_OF_AUDIT_RUNTIME_API_URL": "https://api.proof-of-audit.example.invalid/",
            }
        )

        self.assertEqual(
            config.public_api_base_url(),
            "https://api.proof-of-audit.example.invalid",
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
                                    "execution_mode": "remote_http",
                                    "execution_endpoint": "https://example.invalid/audits",
                                    "publish_path_template": "/audits/{id}/publish",
                                    "challenge_path_template": "/audits/{id}/challenge",
                                    "network": "base-sepolia",
                                    "active": True,
                                    "supported_trust": ["crypto-economic"],
                                    "settlement_mode": "adapter_delegated",
                                    "publication_mode": "api_mediated",
                                    "staking_adapter_kind": "proof_of_audit_stake_adapter",
                                    "staking_adapter_address": "0xfeed",
                                    "staking_adapter_method": "publishStakedAudit",
                                    "publication_scope": "submit_selected_claim",
                                    "registry_contract_address": "0x456",
                                    "validation_registry_address": "0x789",
                                    "validation_source": "erc8004-official",
                                    "validation_request_path_template": "/audits/{id}/validation/request",
                                    "validation_response_path_template": "/audits/{id}/validation/response",
                                    "reputation_registry_address": "0xabc",
                                    "reputation_source": "project-local-custom",
                                    "reputation_path_template": "/auditors/{id}/reputation",
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
            self.assertEqual(config.auditor_services[1].execution_mode, "remote_http")
            self.assertEqual(
                config.auditor_services[1].execution_endpoint,
                "https://example.invalid/audits",
            )
            self.assertEqual(
                config.auditor_services[1].settlement_mode,
                "adapter_delegated",
            )
            self.assertEqual(
                config.auditor_services[1].staking_adapter_address,
                "0xfeed",
            )
            self.assertIsNotNone(
                config.auditor_registration_document_by_service_id("external-auditor")
            )
            self.assertEqual(
                config.auditor_services[1].reputation_path_template,
                "/auditors/{id}/reputation",
            )


# Four valid, distinct secp256k1 private keys (and their derived addresses) used
# by the key-separation tests. Each maps to a different trust role.
_PUBLISHER_KEY = "0x59c6995e998f97a5a0044966f094538e5d8f7c6f8b3631d8c0eb1f68d6f6c7e6"
_ARBITER_KEY = "0x8b3a350cf5c34c9194ca3a545d0f15e3b8f1f0d0c2e5b2f5d7a9a1f6715f89fd"
_VALIDATOR_KEY = "0x0dbbe8ebf7d0313f4fd5401397cbe8bb8d65b1b845a70d820ee7da8db36805b4"
_REPUTATION_KEY = "0x5de4111a884cc4ff8f4b78a1810d7a2ec61b0ff7dd86e31ed5c8984f1a58dc6b"


class KeySeparationTest(unittest.TestCase):
    def _config(self, env: dict[str, str]) -> ContractConfig:
        base = {
            "PROOF_OF_AUDIT_NETWORK": "base-sepolia",
            "PROOF_OF_AUDIT_CHAIN_ID": "84532",
        }
        base.update(env)
        return ContractConfig.from_env(base)

    def test_is_local_network_classification(self) -> None:
        self.assertTrue(
            self._config({"PROOF_OF_AUDIT_NETWORK": "anvil-local"}).is_local_network()
        )
        self.assertTrue(
            self._config(
                {"PROOF_OF_AUDIT_NETWORK": "anvil-system-e2e"}
            ).is_local_network()
        )
        self.assertTrue(
            self._config({"PROOF_OF_AUDIT_NETWORK": "eth-tester"}).is_local_network()
        )
        self.assertFalse(
            self._config({"PROOF_OF_AUDIT_NETWORK": "base-sepolia"}).is_local_network()
        )

    def test_all_distinct_keys_have_no_violations(self) -> None:
        config = self._config(
            {
                "PROOF_OF_AUDIT_PRIVATE_KEY": _PUBLISHER_KEY,
                "PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY": _ARBITER_KEY,
                "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY": _VALIDATOR_KEY,
                "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY": _REPUTATION_KEY,
            }
        )
        self.assertEqual(config.key_separation_violations(), [])

    def test_arbiter_fallback_to_publisher_is_violation(self) -> None:
        # Arbiter key unset -> cascades to the publisher key.
        config = self._config(
            {
                "PROOF_OF_AUDIT_PRIVATE_KEY": _PUBLISHER_KEY,
                "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY": _VALIDATOR_KEY,
                "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY": _REPUTATION_KEY,
            }
        )
        violations = config.key_separation_violations()
        self.assertEqual(len(violations), 1)
        self.assertIn("arbiter and publisher share signing address", violations[0])
        self.assertIn(
            address_from_private_key(_PUBLISHER_KEY),
            violations[0],
        )

    def test_reputation_operator_fallback_is_violation(self) -> None:
        # Reputation-operator key unset -> cascades through validator/arbiter to
        # the publisher key when those are also unset.
        config = self._config(
            {
                "PROOF_OF_AUDIT_PRIVATE_KEY": _PUBLISHER_KEY,
                "PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY": _ARBITER_KEY,
                "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY": _VALIDATOR_KEY,
            }
        )
        violations = config.key_separation_violations()
        # Reputation-operator falls back to validator first.
        self.assertEqual(len(violations), 1)
        self.assertIn(
            "reputation-operator and validator share signing address",
            violations[0],
        )
        self.assertIn(
            address_from_private_key(_VALIDATOR_KEY),
            violations[0],
        )

    def test_reputation_operator_fallback_all_the_way_to_publisher(self) -> None:
        # Only the publisher key is set; arbiter, validator and
        # reputation-operator all cascade down to it -> three pairwise
        # violations sharing the publisher address.
        config = self._config(
            {
                "PROOF_OF_AUDIT_PRIVATE_KEY": _PUBLISHER_KEY,
            }
        )
        violations = config.key_separation_violations()
        publisher_address = address_from_private_key(_PUBLISHER_KEY)
        # All four trust roles cascade to the publisher key -> every pair of the
        # four collides (C(4,2) = 6 pairwise violations).
        self.assertEqual(len(violations), 6)
        for violation in violations:
            self.assertIn(publisher_address, violation)

    def test_challenger_sharing_publisher_is_not_a_violation(self) -> None:
        # Challenger is a convenience signer; sharing the publisher address must
        # not be flagged. All four trust roles are distinct here.
        config = self._config(
            {
                "PROOF_OF_AUDIT_PRIVATE_KEY": _PUBLISHER_KEY,
                "PROOF_OF_AUDIT_CHALLENGER_PRIVATE_KEY": _PUBLISHER_KEY,
                "PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY": _ARBITER_KEY,
                "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY": _VALIDATOR_KEY,
                "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY": _REPUTATION_KEY,
            }
        )
        self.assertEqual(config.key_separation_violations(), [])

    def test_unset_role_keys_are_skipped_without_crashing(self) -> None:
        # No keys configured at all -> nothing to compare, no violations.
        config = self._config({})
        self.assertEqual(config.key_separation_violations(), [])

        # Only validator and reputation-operator set (distinct). Publisher and
        # arbiter have no key and no cascade source, so they resolve to None and
        # are simply skipped -- no crash, no violation.
        partial = self._config(
            {
                "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY": _VALIDATOR_KEY,
                "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY": _REPUTATION_KEY,
            }
        )
        self.assertIsNone(partial.publisher_private_key)
        self.assertIsNone(partial.arbiter_private_key)
        self.assertEqual(partial.key_separation_violations(), [])
