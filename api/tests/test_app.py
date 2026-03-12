import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from proof_of_audit_api.app import create_app


class AuditApiAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        app = create_app(
            Path(self.tempdir.name),
            env_file=Path(self.tempdir.name) / ".env.local",
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
