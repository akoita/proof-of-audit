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
        self.assertFalse(payload["deployment_ready"])

    def test_fixtures_endpoint_returns_generated_manifest(self) -> None:
        response = self.client.get("/fixtures")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["benchmark_id"], "reentrancy-bank")

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

        listed = self.client.get("/audits")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)

        published = self.client.post(
            f"/audits/{audit_id}/publish",
            json={"stake_wei": 10**16, "agent_identity": "auditor-agent-v1"},
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
        self.assertEqual(payload["detail"][0]["loc"][-1], "contract_address")


class AuditApiOnchainPublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        onchain = build_onchain_test_context()
        self.onchain = onchain
        self.chain_id = onchain.contract_config.chain_id
        self.target_address = onchain.web3.eth.accounts[2]
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
            json={"stake_wei": 10**16, "agent_identity": "auditor-agent-v1"},
        )
        self.assertEqual(published.status_code, 200)
        payload = published.json()
        self.assertEqual(payload["status"], "published")
        self.assertEqual(payload["onchain"]["audit_id"], 1)
        self.assertTrue(payload["onchain"]["publish_tx_hash"].startswith("0x"))
        self.assertEqual(payload["onchain"]["stake_wei"], 10**16)
        self.assertEqual(payload["onchain"]["chain_id"], self.chain_id)

        challenged = self.client.post(
            f"/audits/{audit_id}/challenge",
            json={"proof_uri": "ipfs://demo-poc", "challenger": "whitehat-demo"},
        )
        self.assertEqual(challenged.status_code, 200)
        challenge_payload = challenged.json()
        self.assertEqual(challenge_payload["status"], "challenged")
        self.assertEqual(challenge_payload["challenge"]["status"], "opened")
        self.assertEqual(
            challenge_payload["challenge"]["challenger_address"],
            self.client.app.state.audit_service.publisher.account.address,
        )
        self.assertTrue(challenge_payload["challenge"]["challenge_tx_hash"].startswith("0x"))

        duplicate = self.client.post(
            f"/audits/{audit_id}/challenge",
            json={"proof_uri": "ipfs://second-poc", "challenger": "whitehat-2"},
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(duplicate.json()["error"], "invalid_payload")

        resolved = self.client.post(
            f"/audits/{audit_id}/resolve",
            json={"upheld": True, "resolved_by": "arbiter-operator"},
        )
        self.assertEqual(resolved.status_code, 200)
        resolved_payload = resolved.json()
        self.assertEqual(resolved_payload["status"], "resolved")
        self.assertEqual(resolved_payload["challenge"]["status"], "upheld")
        self.assertEqual(resolved_payload["challenge"]["resolution"], "upheld")
        self.assertTrue(resolved_payload["challenge"]["resolve_tx_hash"].startswith("0x"))

        audit_record = self.onchain.contract.functions.getAudit(1).call()
        self.assertEqual(int(audit_record[10]), 3)
        self.assertEqual(int(audit_record[11]), 1)
