import tempfile
import unittest
from pathlib import Path
import json

from fastapi.testclient import TestClient

from proof_of_audit_api.app import create_app


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
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["status"], "published")

        challenged = self.client.post(
            f"/audits/{audit_id}/challenge",
            json={"proof_uri": "ipfs://demo-poc", "challenger": "whitehat"},
        )
        self.assertEqual(challenged.status_code, 200)
        self.assertEqual(challenged.json()["status"], "challenged")
        self.assertEqual(challenged.json()["challenge"]["status"], "accepted")

        fetched = self.client.get(f"/audits/{audit_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], audit_id)

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
