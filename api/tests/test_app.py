import tempfile
import unittest
from pathlib import Path
import json

from fastapi.testclient import TestClient

from proof_of_audit_api.app import create_app
from proof_of_audit_api.service import AuditService
from helpers import build_onchain_test_context

def load_base_sepolia_manifest() -> dict[str, object]:
    return json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "deployments"
            / "base-sepolia.json"
        ).read_text(encoding="utf-8")
    )


class AuditApiAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        data_root = Path(self.tempdir.name) / "data"
        data_root.mkdir()
        fixtures_file = Path(self.tempdir.name) / "demo-fixtures.localhost.json"
        fixtures_file.write_text(
            json.dumps(
                {
                    "fixtures": [
                        {
                            "id": "vulnerable-bank",
                            "label": "Vulnerable Bank",
                            "contract_name": "VulnerableBank",
                            "entry_contract": "VulnerableBank",
                            "benchmark_id": "reentrancy-bank",
                            "address": "0x1000000000000000000000000000000000000001",
                            "challenge_proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
                            "note": "High-confidence reentrancy finding",
                            "source_path": "demo/contracts/VulnerableBank.sol",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        env_file = Path(self.tempdir.name) / ".env.local"
        env_file.write_text(
            f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={fixtures_file}\n",
            encoding="utf-8",
        )
        app = create_app(
            data_root,
            env_file=env_file,
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_healthcheck(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_public_config_endpoint(self) -> None:
        manifest = load_base_sepolia_manifest()
        response = self.client.get("/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["network"], "base-sepolia")
        self.assertEqual(payload["chain_id"], 84532)
        self.assertEqual(payload["auditor"]["id"], "proof-of-audit-auditor")
        self.assertEqual(
            payload["auditor"]["manifest_schema"],
            "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        )
        self.assertEqual(
            payload["auditor"]["type"],
            "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        )
        self.assertEqual(payload["auditor"]["service_type"], "audit_contract")
        self.assertEqual(
            payload["auditor_service"]["service_id"],
            "proof-of-audit-auditor",
        )
        self.assertEqual(payload["auditor_service"]["registration_kind"], "offchain_manifest")
        self.assertEqual(
            payload["auditor_service"]["registration_type"],
            "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        )
        self.assertEqual(
            payload["auditor_service"]["registration_uri"],
            "https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json",
        )
        self.assertEqual(
            payload["auditor_service"]["agent_id"],
            manifest["auditor_identity"]["agent_id"],
        )
        self.assertEqual(
            payload["auditor_service"]["agent_registry"],
            manifest["auditor_identity"]["registry_address"],
        )
        self.assertEqual(
            payload["auditor_service"]["identity_source"],
            manifest["auditor_identity"]["source"],
        )
        self.assertEqual(
            payload["auditor_service"]["validation_registry_address"],
            manifest["validation_bridge"]["registry_address"],
        )
        self.assertEqual(
            payload["auditor_service"]["validation_source"],
            "erc8004-official",
        )
        self.assertEqual(
            payload["auditor_service"]["submission_modes"],
            ["demo_fixture", "deployed_address", "source_bundle", "repository_url"],
        )
        self.assertEqual(
            payload["auditor_service"]["resolution_modes"],
            ["deterministic", "manual_fallback"],
        )
        self.assertTrue(payload["auditor_service"]["deterministic_resolution_supported"])
        self.assertTrue(payload["auditor_service"]["manual_fallback_supported"])
        self.assertEqual(payload["auditor_service"]["discovery_path"], "/auditor")
        self.assertTrue(payload["auditor_service"]["manifest_hash"])
        self.assertFalse(payload["deployment_ready"])

    def test_auditor_endpoint_returns_service_record(self) -> None:
        manifest = load_base_sepolia_manifest()
        response = self.client.get("/auditor")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["service_id"], "proof-of-audit-auditor")
        self.assertEqual(payload["capability"], "audit_contract")
        self.assertEqual(payload["registration_kind"], "offchain_manifest")
        self.assertEqual(
            payload["registration_uri"],
            "https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json",
        )
        self.assertEqual(
            payload["agent_id"],
            manifest["auditor_identity"]["agent_id"],
        )
        self.assertEqual(
            payload["agent_registry"],
            manifest["auditor_identity"]["registry_address"],
        )
        self.assertEqual(
            payload["identity_source"],
            manifest["auditor_identity"]["source"],
        )
        self.assertEqual(
            payload["validation_registry_address"],
            manifest["validation_bridge"]["registry_address"],
        )
        self.assertEqual(payload["validation_source"], "erc8004-official")
        self.assertEqual(
            payload["submission_modes"],
            ["demo_fixture", "deployed_address", "source_bundle", "repository_url"],
        )
        self.assertEqual(
            payload["resolution_modes"],
            ["deterministic", "manual_fallback"],
        )
        self.assertTrue(payload["deterministic_resolution_supported"])
        self.assertTrue(payload["manual_fallback_supported"])
        self.assertEqual(payload["submit_path"], "/audits")
        self.assertEqual(payload["publish_path_template"], "/audits/{id}/publish")
        self.assertEqual(payload["challenge_path_template"], "/audits/{id}/challenge")
        self.assertEqual(
            payload["validation_request_path_template"],
            "/audits/{id}/validation/request",
        )
        self.assertTrue(payload["manifest_hash"])

    def test_plural_auditor_endpoints_list_and_resolve_catalog_entries(self) -> None:
        catalog_file = Path(self.tempdir.name) / "auditors.catalog.json"
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
        catalog_env_file = Path(self.tempdir.name) / "catalog.env.local"
        catalog_env_file.write_text(
            "\n".join(
                [
                    f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={Path(self.tempdir.name) / 'demo-fixtures.localhost.json'}",
                    f"PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE={catalog_file}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        client = TestClient(
            create_app(
                Path(self.tempdir.name) / "catalog-data",
                env_file=catalog_env_file,
            )
        )

        listed = client.get("/auditors")
        self.assertEqual(listed.status_code, 200)
        listed_payload = listed.json()
        self.assertEqual(len(listed_payload["items"]), 2)
        self.assertEqual(
            listed_payload["items"][0]["service_id"],
            "proof-of-audit-auditor",
        )
        self.assertEqual(
            listed_payload["items"][1]["service_id"],
            "external-auditor",
        )

        detail = client.get("/auditors/external-auditor")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["registration_uri"], "https://example.invalid/external-auditor.json")

        registration = client.get("/auditors/external-auditor/registration")
        self.assertEqual(registration.status_code, 200)
        self.assertEqual(registration.json()["name"], "External Auditor")

        missing = client.get("/auditors/unknown-auditor")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"], "auditor_not_found")

    def test_auditor_registration_endpoint_returns_registration_document(self) -> None:
        manifest = load_base_sepolia_manifest()
        response = self.client.get("/auditor/registration")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["type"],
            "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        )
        self.assertEqual(payload["supportedTrust"], ["crypto-economic"])
        self.assertEqual(payload["x-proof-of-audit"]["id"], "proof-of-audit-auditor")
        self.assertEqual(
            payload["services"][1]["endpoint"],
            "https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json",
        )
        self.assertEqual(
            payload["registrations"][0]["agentRegistry"],
            manifest["auditor_identity"]["registry_address"],
        )
        self.assertEqual(
            payload["x-proof-of-audit"]["validationRegistryAddress"],
            manifest["validation_bridge"]["registry_address"],
        )

    def test_fixtures_endpoint_returns_generated_manifest(self) -> None:
        response = self.client.get("/fixtures")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["benchmark_id"], "reentrancy-bank")
        self.assertEqual(
            payload["items"][0]["challenge_proof_uri"],
            "ipfs://reentrancy-bank/withdraw-drain",
        )

    def test_full_audit_flow(self) -> None:
        created = self.client.post(
            "/audits",
            json={
                "contract_address": "0x1000000000000000000000000000000000000001",
                "submitted_by": "integration-test",
            },
        )
        self.assertEqual(created.status_code, 201)
        created_payload = created.json()
        audit_id = created_payload["id"]
        self.assertEqual(created_payload["agent"]["id"], "proof-of-audit-auditor")
        self.assertEqual(created_payload["agent"]["name"], "Proof-of-Audit Auditor")
        self.assertEqual(created_payload["report"]["finding_count"], 1)
        self.assertEqual(
            created_payload["report"]["findings"][0]["finding_id"],
            "reentrancy-bank.withdraw.reentrancy",
        )

        listed = self.client.get("/audits")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)
        self.assertEqual(
            listed.json()["items"][0]["target_key"],
            "0x1000000000000000000000000000000000000001",
        )
        self.assertEqual(
            listed.json()["items"][0]["target_auditor_key"],
            "0x1000000000000000000000000000000000000001::proof-of-audit-auditor",
        )

        published = self.client.post(
            f"/audits/{audit_id}/publish",
            json={"stake_wei": 10**16},
        )
        self.assertEqual(published.status_code, 503)
        self.assertEqual(published.json()["error"], "onchain_not_configured")

        challenged = self.client.post(
            f"/audits/{audit_id}/challenge",
            json={"proof_uri": "ipfs://demo-poc", "challenger": "whitehat"},
        )
        self.assertEqual(challenged.status_code, 400)
        self.assertEqual(challenged.json()["error"], "invalid_payload")

        resolved = self.client.post(
            f"/audits/{audit_id}/resolve",
            json={"upheld": True, "resolved_by": "arbiter-operator"},
        )
        self.assertEqual(resolved.status_code, 400)
        self.assertEqual(resolved.json()["error"], "invalid_payload")

    def test_publish_unknown_audit_returns_404(self) -> None:
        response = self.client.post(
            "/audits/does-not-exist/publish",
            json={"stake_wei": 10**16, "agent_identity": "auditor-agent-v1"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "audit_not_found")

    def test_validation_documents_are_exposed_for_published_and_resolved_audits(self) -> None:
        onchain = build_onchain_test_context()
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
            )
            client = TestClient(create_app(Path(tmpdir), audit_service=service))
            created = client.post(
                "/audits",
                json={
                    "contract_address": "0x1000000000000000000000000000000000000001",
                    "submitted_by": "validation-docs",
                },
            )
            audit_id = created.json()["id"]
            published = client.post(
                f"/audits/{audit_id}/publish",
                json={"stake_wei": 10**16},
            )
            self.assertEqual(published.status_code, 200)
            request_doc = client.get(f"/audits/{audit_id}/validation/request")
            self.assertEqual(request_doc.status_code, 200)
            request_payload = request_doc.json()
            self.assertEqual(
                request_payload["type"],
                "https://eips.ethereum.org/EIPS/eip-8004#validation-request-v1",
            )
            self.assertEqual(request_payload["requestType"], "proof-of-audit.audit-claim")
            self.assertEqual(request_payload["agentId"], 1)

            missing_response = client.get(f"/audits/{audit_id}/validation/response")
            self.assertEqual(missing_response.status_code, 404)
            self.assertEqual(
                missing_response.json()["error"],
                "validation_response_not_found",
            )

            challenged = client.post(
                f"/audits/{audit_id}/challenge",
                json={
                    "proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
                    "challenger": "whitehat",
                },
            )
            self.assertEqual(challenged.status_code, 200)
            response_doc = client.get(f"/audits/{audit_id}/validation/response")
            self.assertEqual(response_doc.status_code, 200)
            response_payload = response_doc.json()
            self.assertEqual(
                response_payload["type"],
                "https://eips.ethereum.org/EIPS/eip-8004#validation-response-v1",
            )
            self.assertEqual(response_payload["response"], 100)
            self.assertEqual(response_payload["tag"], "claim-confirmed")

    def test_validation_error_is_structured(self) -> None:
        response = self.client.post("/audits", json={"submitted_by": "missing-address"})

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"], "validation_error")
        self.assertIn(
            "contract_address is required for deployed_address submissions",
            payload["detail"][0]["msg"],
        )

    def test_list_audits_normalizes_legacy_records(self) -> None:
        legacy_record = {
            "id": "legacy-audit",
            "contract_address": "0x1000000000000000000000000000000000000001",
            "submitted_by": "legacy-user",
            "status": "draft",
            "created_at": "2026-03-14T10:00:00+00:00",
            "report": {
                "benchmark_id": "reentrancy-bank",
                "contract_address": "0x1000000000000000000000000000000000000001",
                "summary": "Withdraw updates balance after the external call.",
                "findings": [
                    {
                        "title": "Reentrancy in withdraw()",
                        "severity": "high",
                        "description": "ETH is sent to msg.sender before accounting is updated.",
                        "recommendation": "Apply checks-effects-interactions.",
                        "detector": "pattern.reentrancy",
                    }
                ],
                "supported_checks": [
                    "reentrancy",
                    "access_control",
                    "unchecked_external_call",
                ],
                "confidence": "high",
                "report_hash": "legacy-report-hash",
                "metadata_hash": "legacy-metadata-hash",
                "max_severity": 3,
            },
            "onchain": None,
            "challenge": None,
        }
        (Path(self.tempdir.name) / "data" / "legacy-audit.json").write_text(
            json.dumps(legacy_record, indent=2),
            encoding="utf-8",
        )

        response = self.client.get("/audits")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["submission"]["input_kind"], "deployed_address")
        self.assertEqual(payload["items"][0]["agent"]["id"], "proof-of-audit-auditor")
        self.assertEqual(
            payload["items"][0]["target_auditor_key"],
            "0x1000000000000000000000000000000000000001::proof-of-audit-auditor",
        )
        self.assertEqual(payload["items"][0]["report"]["finding_count"], 1)
        self.assertEqual(
            payload["items"][0]["report"]["findings"][0]["category"],
            "reentrancy",
        )

    def test_richer_multi_finding_report_shape_is_exposed(self) -> None:
        response = self.client.post(
            "/audits",
            json={
                "contract_address": "0x1000000000000000000000000000000000000004",
                "submitted_by": "schema-check",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["report"]["benchmark_id"], "dual-risk-vault")
        self.assertEqual(payload["agent"]["id"], "proof-of-audit-auditor")
        self.assertEqual(payload["report"]["finding_count"], 2)
        self.assertEqual(payload["report"]["severity_breakdown"]["high"], 1)
        self.assertEqual(payload["report"]["severity_breakdown"]["medium"], 1)
        self.assertEqual(
            payload["report"]["findings"][0]["category"],
            "access_control",
        )
        self.assertEqual(
            payload["report"]["findings"][1]["affected_function"],
            "emergencyPayout(uint256)",
        )

    def test_list_audits_supports_target_filter_and_target_path(self) -> None:
        first = self.client.post(
            "/audits",
            json={
                "contract_address": "0x1000000000000000000000000000000000000001",
                "submitted_by": "first",
            },
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            "/audits",
            json={
                "contract_address": "0x1000000000000000000000000000000000000002",
                "submitted_by": "second",
            },
        )
        self.assertEqual(second.status_code, 201)
        third = self.client.post(
            "/audits",
            json={
                "contract_address": "0x1000000000000000000000000000000000000001",
                "submitted_by": "third",
            },
        )
        self.assertEqual(third.status_code, 201)

        filtered = self.client.get(
            "/audits",
            params={"contract_address": "0x1000000000000000000000000000000000000001"},
        )
        self.assertEqual(filtered.status_code, 200)
        filtered_payload = filtered.json()
        self.assertEqual(len(filtered_payload["items"]), 2)
        self.assertTrue(
            all(
                item["contract_address"] == "0x1000000000000000000000000000000000000001"
                for item in filtered_payload["items"]
            )
        )

        target_view = self.client.get(
            "/targets/0x1000000000000000000000000000000000000001/audits"
        )
        self.assertEqual(target_view.status_code, 200)
        target_payload = target_view.json()
        self.assertEqual(
            target_payload["target_contract"],
            "0x1000000000000000000000000000000000000001",
        )
        self.assertEqual(
            target_payload["target_key"],
            "0x1000000000000000000000000000000000000001",
        )
        self.assertEqual(len(target_payload["items"]), 2)


class AuditApiOnchainPublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        onchain = build_onchain_test_context()
        self.onchain = onchain
        self.chain_id = onchain.contract_config.chain_id
        self.target_address = "0x1000000000000000000000000000000000000001"
        service = AuditService(
            Path(self.tempdir.name) / "data",
            contract_config=onchain.contract_config,
            publisher=onchain.publisher,
            arbiter_client=onchain.arbiter_client,
        )
        app = create_app(audit_service=service)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_publish_persists_real_transaction_data(self) -> None:
        created = self.client.post(
            "/audits",
            json={
                "contract_address": self.target_address,
                "submitted_by": "integration-test",
            },
        )
        self.assertEqual(created.status_code, 201)
        audit_id = created.json()["id"]

        published = self.client.post(
            f"/audits/{audit_id}/publish",
            json={"stake_wei": 10**16},
        )
        self.assertEqual(published.status_code, 200)
        payload = published.json()
        self.assertEqual(payload["status"], "published")
        self.assertEqual(payload["agent"]["id"], "proof-of-audit-auditor")
        self.assertEqual(payload["onchain"]["audit_id"], 1)
        self.assertEqual(payload["onchain"]["agent_identity"], "proof-of-audit-auditor")
        self.assertEqual(payload["onchain"]["agent_name"], "Proof-of-Audit Auditor")
        self.assertTrue(payload["onchain"]["publish_tx_hash"].startswith("0x"))
        self.assertEqual(payload["onchain"]["stake_wei"], 10**16)
        self.assertEqual(payload["onchain"]["chain_id"], self.chain_id)

        challenged = self.client.post(
            f"/audits/{audit_id}/challenge",
            json={
                "proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
                "challenger": "whitehat-demo",
            },
        )
        self.assertEqual(challenged.status_code, 200)
        challenge_payload = challenged.json()
        self.assertEqual(challenge_payload["status"], "resolved")
        self.assertEqual(challenge_payload["challenge"]["status"], "rejected")
        self.assertEqual(challenge_payload["challenge"]["resolution"], "rejected")
        self.assertEqual(
            challenge_payload["challenge"]["verification_status"],
            "verified",
        )
        self.assertEqual(
            challenge_payload["challenge"]["resolution_path"],
            "deterministic",
        )
        self.assertEqual(
            challenge_payload["challenge"]["challenger_address"],
            self.client.app.state.audit_service.publisher.account.address,
        )
        self.assertTrue(challenge_payload["challenge"]["challenge_tx_hash"].startswith("0x"))
        self.assertTrue(challenge_payload["challenge"]["resolve_tx_hash"].startswith("0x"))

        audit_record = self.onchain.contract.functions.getAudit(1).call()
        self.assertEqual(int(audit_record[10]), 3)
        self.assertEqual(int(audit_record[11]), 2)

    def test_invalid_challenge_evidence_stays_open(self) -> None:
        created = self.client.post(
            "/audits",
            json={
                "contract_address": "0x1000000000000000000000000000000000000003",
                "submitted_by": "integration-test",
            },
        )
        self.assertEqual(created.status_code, 201)
        audit_id = created.json()["id"]

        published = self.client.post(
            f"/audits/{audit_id}/publish",
            json={"stake_wei": 10**16},
        )
        self.assertEqual(published.status_code, 200)

        challenged = self.client.post(
            f"/audits/{audit_id}/challenge",
            json={"proof_uri": "ipfs://wrong-proof", "challenger": "whitehat-demo"},
        )
        self.assertEqual(challenged.status_code, 200)
        challenge_payload = challenged.json()
        self.assertEqual(challenge_payload["status"], "challenged")
        self.assertEqual(challenge_payload["challenge"]["status"], "opened")
        self.assertEqual(
            challenge_payload["challenge"]["verification_status"],
            "invalid_evidence",
        )
        self.assertEqual(
            challenge_payload["challenge"]["resolution_path"],
            "manual_fallback",
        )
