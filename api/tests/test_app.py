import tempfile
import unittest
from pathlib import Path
import json

from fastapi.testclient import TestClient

from proof_of_audit_api.app import create_app
from proof_of_audit_api.service import AuditService
from helpers import build_onchain_test_context


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
        response = self.client.get("/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["network"], "base-sepolia")
        self.assertEqual(payload["chain_id"], 84532)
        self.assertEqual(payload["auditor"]["id"], "proof-of-audit-auditor")
        self.assertEqual(
            payload["auditor"]["manifest_schema"],
            "proof-of-audit/auditor-service@v1",
        )
        self.assertEqual(payload["auditor"]["service_type"], "audit_contract")
        self.assertEqual(
            payload["auditor_service"]["service_id"],
            "proof-of-audit-auditor",
        )
        self.assertEqual(payload["auditor_service"]["registration_kind"], "offchain_manifest")
        self.assertEqual(payload["auditor_service"]["discovery_path"], "/auditor")
        self.assertTrue(payload["auditor_service"]["manifest_hash"])
        self.assertFalse(payload["deployment_ready"])

    def test_auditor_endpoint_returns_service_record(self) -> None:
        response = self.client.get("/auditor")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["service_id"], "proof-of-audit-auditor")
        self.assertEqual(payload["capability"], "audit_contract")
        self.assertEqual(payload["registration_kind"], "offchain_manifest")
        self.assertEqual(payload["submit_path"], "/audits")
        self.assertEqual(payload["publish_path_template"], "/audits/{id}/publish")
        self.assertEqual(payload["challenge_path_template"], "/audits/{id}/challenge")
        self.assertTrue(payload["manifest_hash"])

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
