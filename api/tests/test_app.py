import tempfile
import unittest
import io
from pathlib import Path
import json
from unittest.mock import Mock, patch
import zipfile
import tempfile as tempfile_module

import httpx
from fastapi.testclient import TestClient

from proof_of_audit_api.app import create_app
from proof_of_audit_api.service import AuditService
from proof_of_audit_agent.challenge_verifier import ChallengeVerificationResult, EvidenceContext
from helpers import build_onchain_test_context

def load_base_sepolia_manifest() -> dict[str, object]:
    return json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "deployments"
            / "base-sepolia.json"
        ).read_text(encoding="utf-8")
    )


def write_fake_agent_forge_script(
    path: Path,
    *,
    report_payload: dict[str, object] | None = None,
    exit_code: int = 0,
    stderr_text: str = "",
    run_id: str = "run-123",
) -> Path:
    report_text = json.dumps(report_payload, indent=2) if report_payload is not None else None
    script = f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
repo = Path(args[args.index("--repo") + 1])
report_path = repo / ".proof-of-audit" / "agent-report.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_text = {report_text!r}
if report_text is not None:
    report_path.write_text(report_text, encoding="utf-8")
run_dir = Path(os.environ["HOME"]) / ".agent-forge" / "runs" / {run_id!r}
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "run.json").write_text(json.dumps({{
    "id": {run_id!r},
    "repo_path": str(repo),
    "state": "completed"
}}), encoding="utf-8")
if {stderr_text!r}:
    sys.stderr.write({stderr_text!r})
sys.exit({exit_code})
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


class FakeHostedHttpClient:
    def __init__(
        self,
        responses: list[dict[str, object]],
        requests: list[dict[str, object]],
    ) -> None:
        self._responses = responses
        self.requests = requests

    def __enter__(self) -> "FakeHostedHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def request(
        self,
        method: str,
        url: str,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        self.requests.append({"method": method, "url": url, "json": json})
        payload = self._responses.pop(0)
        return httpx.Response(
            int(payload.get("status_code", 200)),
            json=payload.get("json"),
            request=httpx.Request(method, url, json=json),
        )


class AuditApiAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        data_root = Path(self.tempdir.name) / "data"
        data_root.mkdir()
        self.data_root = data_root
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
            "\n".join(
                [
                    "PROOF_OF_AUDIT_NETWORK=anvil-local",
                    "PROOF_OF_AUDIT_CHAIN_ID=31337",
                    f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={fixtures_file}",
                ]
            )
            + "\n",
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

    def test_source_bundle_upload_persists_sol_file_and_returns_local_path(self) -> None:
        response = self.client.post(
            "/source-bundles/upload",
            json={
                "filename": "UncheckedTreasury.sol",
                "content_base64": "cHJhZ21hIHNvbGlkaXR5IF4wLjguMjg7CmNvbnRyYWN0IFVuY2hlY2tlZFRyZWFzdXJ5IHt9Cg==",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        uploaded_path = Path(payload["source_bundle_uri"])
        self.assertTrue(uploaded_path.exists())
        self.assertEqual(uploaded_path.suffix, ".sol")
        self.assertEqual(payload["storage_backend"], "local")
        self.assertEqual(payload["source_bundle_label"], "UncheckedTreasury")
        self.assertEqual(payload["entry_contract"], "UncheckedTreasury")
        self.assertEqual(
            uploaded_path.read_text(encoding="utf-8"),
            "pragma solidity ^0.8.28;\ncontract UncheckedTreasury {}\n",
        )

    def test_source_bundle_upload_can_store_to_gcs(self) -> None:
        env_file = Path(self.tempdir.name) / ".env.gcs"
        fixtures_file = Path(self.tempdir.name) / "demo-fixtures.gcs.json"
        fixtures_file.write_text('{"fixtures":[]}\n', encoding="utf-8")
        env_file.write_text(
            "\n".join(
                [
                    f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={fixtures_file}",
                    "PROOF_OF_AUDIT_SOURCE_BUNDLE_STORAGE_KIND=gcs",
                    "PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_BUCKET=proof-of-audit-bundles",
                    "PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_PREFIX=uploads/source-bundles",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        class FakeBlob:
            def __init__(self, name: str) -> None:
                self.name = name
                self.uploaded: bytes | None = None
                self.content_type: str | None = None

            def upload_from_string(self, payload: bytes, content_type: str | None = None) -> None:
                self.uploaded = payload
                self.content_type = content_type

        class FakeBucket:
            def __init__(self) -> None:
                self.last_blob: FakeBlob | None = None

            def blob(self, name: str) -> FakeBlob:
                self.last_blob = FakeBlob(name)
                return self.last_blob

        class FakeStorageClient:
            def __init__(self) -> None:
                self.last_bucket_name: str | None = None
                self.last_bucket = FakeBucket()

            def bucket(self, name: str) -> FakeBucket:
                self.last_bucket_name = name
                return self.last_bucket

        fake_storage_client = FakeStorageClient()
        fake_storage_module = type(
            "FakeStorageModule",
            (),
            {"Client": lambda self=None: fake_storage_client},
        )()
        with patch(
            "proof_of_audit_api.source_bundle_storage._require_gcs_storage",
            return_value=fake_storage_module,
        ):
            client = TestClient(
                create_app(Path(self.tempdir.name) / "gcs-data", env_file=env_file)
            )
            response = client.post(
                "/source-bundles/upload",
                json={
                    "filename": "UncheckedTreasury.sol",
                    "content_base64": "cHJhZ21hIHNvbGlkaXR5IF4wLjguMjg7CmNvbnRyYWN0IFVuY2hlY2tlZFRyZWFzdXJ5IHt9Cg==",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["storage_backend"], "gcs")
        self.assertTrue(
            payload["source_bundle_uri"].startswith(
                "gs://proof-of-audit-bundles/uploads/source-bundles/UncheckedTreasury-"
            )
        )
        self.assertEqual(fake_storage_client.last_bucket_name, "proof-of-audit-bundles")
        self.assertIsNotNone(fake_storage_client.last_bucket.last_blob)
        self.assertEqual(
            fake_storage_client.last_bucket.last_blob.content_type,
            "text/plain; charset=utf-8",
        )
        self.assertEqual(
            fake_storage_client.last_bucket.last_blob.uploaded,
            b"pragma solidity ^0.8.28;\ncontract UncheckedTreasury {}\n",
        )

    def test_source_bundle_upload_can_store_to_ipfs(self) -> None:
        env_file = Path(self.tempdir.name) / ".env.ipfs"
        fixtures_file = Path(self.tempdir.name) / "demo-fixtures.ipfs.json"
        fixtures_file.write_text('{"fixtures":[]}\n', encoding="utf-8")
        env_file.write_text(
            "\n".join(
                [
                    f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={fixtures_file}",
                    "PROOF_OF_AUDIT_SOURCE_BUNDLE_STORAGE_KIND=ipfs",
                    "PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_API_URL=http://127.0.0.1:5001",
                    "PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_AUTH_HEADER=Authorization: Bearer token-123",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._buffer = io.BytesIO(payload)

            def read(self, size: int = -1) -> bytes:
                return self._buffer.read(size)

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                del exc_type, exc, tb

        def fake_urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
            self.assertEqual(timeout, 30)
            self.assertIn("/api/v0/add?pin=true&wrap-with-directory=true", req.full_url)
            self.assertEqual(req.headers["Authorization"], "Bearer token-123")
            return FakeResponse(
                b'{"Name":"UncheckedTreasury.sol","Hash":"bafyfile"}\n'
                b'{"Name":"","Hash":"bafydirectory"}\n'
            )

        with patch("proof_of_audit_api.source_bundle_storage.request.urlopen", side_effect=fake_urlopen):
            client = TestClient(
                create_app(Path(self.tempdir.name) / "ipfs-data", env_file=env_file)
            )
            response = client.post(
                "/source-bundles/upload",
                json={
                    "filename": "UncheckedTreasury.sol",
                    "content_base64": "cHJhZ21hIHNvbGlkaXR5IF4wLjguMjg7CmNvbnRyYWN0IFVuY2hlY2tlZFRyZWFzdXJ5IHt9Cg==",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["storage_backend"], "ipfs")
        self.assertEqual(
            payload["source_bundle_uri"],
            "ipfs://bafydirectory/UncheckedTreasury.sol",
        )

    def test_source_bundle_upload_rejects_unsupported_extensions(self) -> None:
        response = self.client.post(
            "/source-bundles/upload",
            json={
                "filename": "notes.txt",
                "content_base64": "bm90IGEgY29udHJhY3QK",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_upload")

    def test_create_app_accepts_cloudsql_postgres_store_settings(self) -> None:
        env_file = Path(self.tempdir.name) / ".env.cloudsql"
        fixtures_file = Path(self.tempdir.name) / "demo-fixtures.localhost.json"
        env_file.write_text(
            "\n".join(
                [
                    f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={fixtures_file}",
                    "PROOF_OF_AUDIT_STORE_KIND=cloudsql-postgres",
                    "PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME=project:region:instance",
                    "PROOF_OF_AUDIT_STORE_DATABASE=proof_of_audit",
                    "PROOF_OF_AUDIT_STORE_USER=auditor@example.iam",
                    "PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH=true",
                    "PROOF_OF_AUDIT_STORE_PATH=ignored-for-cloudsql",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        store = Mock()
        store.close = Mock()

        with patch("proof_of_audit_api.service.create_store", return_value=store) as create_store_mock:
            with TestClient(create_app(Path(self.tempdir.name) / "cloudsql-data", env_file=env_file)) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        create_store_mock.assert_called_once()
        kwargs = create_store_mock.call_args.kwargs
        self.assertEqual(kwargs["kind"], "cloudsql-postgres")
        self.assertIsNone(kwargs["database_path"])
        self.assertEqual(
            kwargs["postgres_config"].instance_connection_name,
            "project:region:instance",
        )
        self.assertTrue(kwargs["postgres_config"].enable_iam_auth)
        store.close.assert_called_once()

    def test_public_config_endpoint(self) -> None:
        response = self.client.get("/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["network"], "anvil-local")
        self.assertEqual(payload["chain_id"], 31337)
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
        self.assertIsNone(payload["auditor_service"]["agent_id"])
        self.assertIsNone(payload["auditor_service"]["agent_registry"])
        self.assertIsNone(payload["auditor_service"]["identity_source"])
        self.assertIsNone(payload["auditor_service"]["validation_registry_address"])
        self.assertIsNone(payload["auditor_service"]["validation_source"])
        self.assertEqual(
            payload["auditor_service"]["reputation_path_template"],
            "/auditors/{id}/reputation",
        )
        self.assertEqual(
            payload["auditor_service"]["submission_modes"],
            ["demo_fixture", "deployed_address", "source_bundle", "repository_url"],
        )
        self.assertEqual(
            payload["auditor_service"]["resolution_modes"],
            ["advisory_verifier", "manual_fallback"],
        )
        self.assertFalse(payload["auditor_service"]["deterministic_resolution_supported"])
        self.assertTrue(payload["auditor_service"]["manual_fallback_supported"])
        self.assertEqual(payload["auditor_service"]["discovery_path"], "/auditor")
        self.assertEqual(payload["auditor_service"]["execution_mode"], "local_worker")
        self.assertIsNone(payload["auditor_service"]["execution_endpoint"])
        self.assertEqual(
            payload["auditor_service"]["settlement_mode"],
            "native_proof_of_audit",
        )
        self.assertEqual(payload["auditor_service"]["publication_mode"], "api_mediated")
        self.assertEqual(
            payload["auditor_service"]["staking_adapter_kind"],
            "native_proof_of_audit",
        )
        self.assertIsNone(payload["auditor_service"]["staking_adapter_address"])
        self.assertEqual(
            payload["auditor_service"]["staking_adapter_method"],
            "publishAudit",
        )
        self.assertEqual(
            payload["auditor_service"]["publication_scope"],
            "submit_selected_claim",
        )
        self.assertTrue(payload["auditor_service"]["manifest_hash"])
        self.assertEqual(payload["auditor_service"]["reputation"]["score"], 50)
        self.assertEqual(payload["auditor_service"]["reputation"]["band"], "provisional")
        self.assertFalse(payload["deployment_ready"])

    def test_auditor_endpoint_returns_service_record(self) -> None:
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
        self.assertIsNone(payload["agent_id"])
        self.assertIsNone(payload["agent_registry"])
        self.assertIsNone(payload["identity_source"])
        self.assertIsNone(payload["validation_registry_address"])
        self.assertIsNone(payload["validation_source"])
        self.assertEqual(
            payload["submission_modes"],
            ["demo_fixture", "deployed_address", "source_bundle", "repository_url"],
        )
        self.assertEqual(
            payload["resolution_modes"],
            ["advisory_verifier", "manual_fallback"],
        )
        self.assertFalse(payload["deterministic_resolution_supported"])
        self.assertTrue(payload["manual_fallback_supported"])
        self.assertEqual(payload["submit_path"], "/audits")
        self.assertEqual(payload["execution_mode"], "local_worker")
        self.assertIsNone(payload["execution_endpoint"])
        self.assertEqual(payload["settlement_mode"], "native_proof_of_audit")
        self.assertEqual(payload["publication_mode"], "api_mediated")
        self.assertEqual(payload["staking_adapter_kind"], "native_proof_of_audit")
        self.assertIsNone(payload["staking_adapter_address"])
        self.assertEqual(payload["staking_adapter_method"], "publishAudit")
        self.assertEqual(payload["publication_scope"], "submit_selected_claim")
        self.assertEqual(payload["publish_path_template"], "/audits/{id}/publish")
        self.assertEqual(payload["challenge_path_template"], "/audits/{id}/challenge")
        self.assertEqual(
            payload["validation_request_path_template"],
            "/audits/{id}/validation/request",
        )
        self.assertEqual(payload["reputation_path_template"], "/auditors/{id}/reputation")
        self.assertEqual(payload["reputation"]["score"], 50)
        self.assertEqual(payload["reputation"]["resolved_challenge_count"], 0)
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
        self.assertEqual(listed_payload["items"][1]["execution_mode"], "remote_http")
        self.assertEqual(
            listed_payload["items"][1]["execution_endpoint"],
            "https://example.invalid/audits",
        )
        self.assertEqual(
            listed_payload["items"][1]["settlement_mode"],
            "adapter_delegated",
        )
        self.assertEqual(
            listed_payload["items"][1]["staking_adapter_address"],
            "0xfeed",
        )
        self.assertEqual(listed_payload["items"][0]["reputation"]["score"], 50)
        self.assertEqual(listed_payload["items"][1]["reputation"]["band"], "provisional")

        detail = client.get("/auditors/external-auditor")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["registration_uri"], "https://example.invalid/external-auditor.json")
        self.assertEqual(detail.json()["publication_mode"], "api_mediated")
        self.assertEqual(detail.json()["reputation"]["resolved_challenge_count"], 0)

        reputation = client.get("/auditors/external-auditor/reputation")
        self.assertEqual(reputation.status_code, 200)
        self.assertEqual(reputation.json()["service_id"], "external-auditor")
        self.assertEqual(reputation.json()["reputation"]["score"], 50)

        registration = client.get("/auditors/external-auditor/registration")
        self.assertEqual(registration.status_code, 200)
        self.assertEqual(registration.json()["name"], "External Auditor")

        missing = client.get("/auditors/unknown-auditor")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"], "auditor_not_found")

    def test_marketplace_preview_endpoint_returns_filtered_auditor_matches(self) -> None:
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
        catalog_env_file = Path(self.tempdir.name) / "catalog-preview.env.local"
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
                Path(self.tempdir.name) / "catalog-preview-data",
                env_file=catalog_env_file,
            )
        )

        response = client.post(
            "/marketplace/preview",
            json={
                "contract_address": "0xABCDEF",
                "bounty_wei": 2_000_000_000_000_000_000,
                "protocol_fee_wei": 100_000_000_000_000_000,
                "filters": {
                    "whitelist_mode": "allowlist",
                    "allowed_service_ids": ["external-auditor"],
                    "required_identity_service_id": "external-auditor",
                    "required_identity_agent_id": 7,
                    "required_identity_registry": "0x123",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["target_contract"], "0xabcdef")
        self.assertEqual(payload["request_state"], "preview_only")
        self.assertEqual(payload["chain_context"]["authority"], "chain_authoritative")
        self.assertEqual(payload["cost_breakdown"]["authority"], "api_preview")
        self.assertEqual(payload["cost_breakdown"]["total_wei"], 2_100_000_000_000_000_000)
        self.assertEqual(payload["filters"]["whitelist_mode"], "allowlist")
        self.assertEqual(payload["eligibility_summary"]["total_auditors"], 2)
        self.assertEqual(payload["eligibility_summary"]["eligible_auditors"], 1)
        matches = {item["service_id"]: item for item in payload["auditor_matches"]}
        self.assertFalse(matches["proof-of-audit-auditor"]["eligibility"]["matches"])
        self.assertIn(
            "outside the current allowlist preview",
            " ".join(matches["proof-of-audit-auditor"]["eligibility"]["reasons"]).lower(),
        )
        self.assertTrue(matches["external-auditor"]["eligibility"]["matches"])
        self.assertEqual(matches["external-auditor"]["agent_id"], 7)
        self.assertEqual(matches["external-auditor"]["agent_registry"], "0x123")
        self.assertIn("API-derived previews", payload["preview_disclaimer"])

    def test_request_listing_and_eligibility_endpoints(self) -> None:
        request_catalog = self.data_root / "audit-requests.json"
        request_catalog.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "request_id": "req-open-1",
                            "status": "open",
                            "contract_address": "0x1000000000000000000000000000000000000001",
                            "chain_id": 84532,
                            "bounty_wei": 2_000_000_000_000_000_000,
                            "protocol_fee_wei": 100_000_000_000_000_000,
                            "response_window_end": "2026-03-30T00:00:00Z",
                            "created_at": "2026-03-27T10:00:00Z",
                            "filters": {
                                "whitelist_mode": "allowlist",
                                "allowed_service_ids": ["proof-of-audit-auditor"],
                            },
                            "metadata": {
                                "confidence_hint": "high",
                            },
                        },
                        {
                            "request_id": "req-closed-1",
                            "status": "closed",
                            "contract_address": "0x1000000000000000000000000000000000000002",
                            "bounty_wei": 1_000_000_000_000_000_000,
                        },
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        listed = self.client.get("/requests", params={"status": "open"})
        self.assertEqual(listed.status_code, 200)
        listed_payload = listed.json()
        self.assertEqual(len(listed_payload["items"]), 1)
        self.assertEqual(listed_payload["items"][0]["request_id"], "req-open-1")
        self.assertEqual(listed_payload["items"][0]["filters"]["whitelist_mode"], "allowlist")

        eligibility = self.client.get(
            "/requests/req-open-1/eligibility",
            params={"auditor": "proof-of-audit-auditor"},
        )
        self.assertEqual(eligibility.status_code, 200)
        eligibility_payload = eligibility.json()
        self.assertTrue(eligibility_payload["eligible"])
        self.assertEqual(eligibility_payload["minimum_stake_wei"], 0)
        self.assertIn("Matches the current preview filters.", eligibility_payload["reasons"])

        missing = self.client.get(
            "/requests/unknown-request/eligibility",
            params={"auditor": "proof-of-audit-auditor"},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"], "request_not_found")

    def test_create_request_endpoint_creates_and_reads_onchain_request(self) -> None:
        onchain = build_onchain_test_context()
        service = AuditService(
            Path(self.tempdir.name) / "request-endpoint-data",
            contract_config=onchain.contract_config,
            publisher=onchain.publisher,
            arbiter_client=onchain.arbiter_client,
        )
        client = TestClient(create_app(audit_service=service))

        created = client.post(
            "/requests",
            json={
                "contract_address": onchain.web3.eth.accounts[3],
                "bounty_wei": 2_000_000_000_000_000_000,
                "response_window_seconds": 3600,
                "filters": {
                    "minimum_stake_wei": 0,
                    "whitelist_mode": "allowlist",
                    "allowed_service_ids": ["proof-of-audit-auditor"],
                    "required_identity_registry": onchain.contract_config.auditor_agent_registry,
                    "required_identity_agent_id": 1,
                },
            },
        )

        self.assertEqual(created.status_code, 201)
        created_payload = created.json()
        self.assertEqual(created_payload["request_id"], "1")
        self.assertEqual(created_payload["status"], "open")
        self.assertEqual(
            created_payload["requester"],
            onchain.publisher.account.address.lower(),
        )
        self.assertTrue(created_payload["request_tx_hash"].startswith("0x"))
        self.assertEqual(created_payload["filters"]["whitelist_mode"], "allowlist")

        listed = client.get("/requests", params={"status": "open"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)
        self.assertEqual(listed.json()["items"][0]["request_id"], "1")

        detail = client.get("/requests/1")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["contract_address"], onchain.web3.eth.accounts[3].lower())

        eligibility = client.get(
            "/requests/1/eligibility",
            params={"auditor": "proof-of-audit-auditor"},
        )
        self.assertEqual(eligibility.status_code, 200)
        self.assertTrue(eligibility.json()["eligible"])
        self.assertEqual(eligibility.json()["minimum_stake_wei"], 0)

    def test_auditor_registration_endpoint_returns_registration_document(self) -> None:
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
        self.assertEqual(payload["registrations"], [])
        self.assertEqual(payload["x-proof-of-audit"]["network"], "anvil-local")
        self.assertEqual(payload["x-proof-of-audit"]["chainId"], 31337)

    def test_challenger_feed_endpoint_returns_recent_lifecycle_events(self) -> None:
        onchain = build_onchain_test_context()
        service = AuditService(
            Path(self.tempdir.name) / "challenger-feed-data",
            contract_config=onchain.contract_config,
            publisher=onchain.publisher,
            arbiter_client=onchain.arbiter_client,
            validation_bridge=onchain.validation_bridge,
            reputation_bridge=onchain.reputation_bridge,
        )
        created = service.create_audit(
            onchain.web3.eth.accounts[2],
            submitted_by="judge",
        )
        service.publish_audit(created["id"], 10**16, None)
        service.challenge_audit(
            created["id"],
            "ipfs://demo-poc",
            challenger="whitehat",
        )
        client = TestClient(
            create_app(
                Path(self.tempdir.name) / "challenger-feed-data",
                env_file=Path(self.tempdir.name) / ".env.local",
                audit_service=service,
            )
        )

        response = client.get("/challenger-feed?limit=2")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["event_kind"], "challenge_opened")
        self.assertEqual(payload["items"][1]["event_kind"], "audit_published")
        self.assertEqual(payload["items"][0]["service_id"], "proof-of-audit-auditor")
        self.assertEqual(payload["items"][0]["auditor_name"], "Proof-of-Audit Auditor")
        self.assertEqual(payload["items"][0]["current_state"], "challenged")
        self.assertTrue(payload["items"][0]["publish_tx_hash"].startswith("0x"))
        self.assertTrue(payload["items"][0]["challenge_tx_hash"].startswith("0x"))
        self.assertIsNotNone(payload["items"][0]["challenge_window_end"])
        self.assertEqual(
            payload["items"][0]["verification_dossier_path"],
            f"/audits/{created['id']}/challenge/dossier",
        )
        self.assertEqual(payload["items"][0]["verification_status"], "verifier_unavailable")

    def test_challenge_verification_dossier_endpoint_returns_machine_readable_payload(self) -> None:
        onchain = build_onchain_test_context()
        service = AuditService(
            Path(self.tempdir.name) / "dossier-endpoint-data",
            contract_config=onchain.contract_config,
            publisher=onchain.publisher,
            arbiter_client=onchain.arbiter_client,
        )
        client = TestClient(create_app(audit_service=service))

        created = client.post(
            "/audits",
            json={
                "contract_address": onchain.web3.eth.accounts[2],
                "submitted_by": "integration-test",
            },
        )
        self.assertEqual(created.status_code, 201)
        audit_id = created.json()["id"]
        published = client.post(
            f"/audits/{audit_id}/publish",
            json={"stake_wei": 10**16},
        )
        self.assertEqual(published.status_code, 200)
        challenged = client.post(
            f"/audits/{audit_id}/challenge",
            json={"proof_uri": "ipfs://demo-poc", "challenger": "whitehat-demo"},
        )
        self.assertEqual(challenged.status_code, 200)
        self.assertEqual(
            challenged.json()["challenge"]["verification_dossier_path"],
            f"/audits/{audit_id}/challenge/dossier",
        )

        response = client.get(f"/audits/{audit_id}/challenge/dossier")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "challenge-verifier-dossier/v1")
        self.assertEqual(payload["policy"]["status"], "manual_review_required")
        self.assertEqual(payload["comparison"]["status"], "not_assessed")

    def test_default_auditor_reputation_endpoint_returns_summary(self) -> None:
        response = self.client.get("/auditor/reputation")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["service_id"], "proof-of-audit-auditor")
        self.assertEqual(payload["reputation"]["score"], 50)
        self.assertEqual(payload["reputation"]["band"], "provisional")

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
                reputation_bridge=onchain.reputation_bridge,
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
            reputation_claim = client.get(f"/audits/{audit_id}/reputation/claim")
            self.assertEqual(reputation_claim.status_code, 200)
            reputation_claim_payload = reputation_claim.json()
            self.assertEqual(
                reputation_claim_payload["type"],
                "https://github.com/akoita/proof-of-audit#reputation-claim-v1",
            )
            self.assertEqual(reputation_claim_payload["agentId"], 1)

            missing_response = client.get(f"/audits/{audit_id}/validation/response")
            self.assertEqual(missing_response.status_code, 404)
            self.assertEqual(
                missing_response.json()["error"],
                "validation_response_not_found",
            )
            missing_reputation_resolution = client.get(
                f"/audits/{audit_id}/reputation/resolution"
            )
            self.assertEqual(missing_reputation_resolution.status_code, 404)
            self.assertEqual(
                missing_reputation_resolution.json()["error"],
                "reputation_resolution_not_found",
            )

            challenged = client.post(
                f"/audits/{audit_id}/challenge",
                json={
                    "proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
                    "challenger": "whitehat",
                },
            )
            self.assertEqual(challenged.status_code, 200)
            resolved = client.post(
                f"/audits/{audit_id}/resolve",
                json={
                    "upheld": False,
                    "resolved_by": "arbiter-operator",
                },
            )
            self.assertEqual(resolved.status_code, 200)
            response_doc = client.get(f"/audits/{audit_id}/validation/response")
            self.assertEqual(response_doc.status_code, 200)
            response_payload = response_doc.json()
            self.assertEqual(
                response_payload["type"],
                "https://eips.ethereum.org/EIPS/eip-8004#validation-response-v1",
            )
            self.assertEqual(response_payload["response"], 100)
            self.assertEqual(response_payload["tag"], "claim-confirmed")
            reputation_resolution = client.get(
                f"/audits/{audit_id}/reputation/resolution"
            )
            self.assertEqual(reputation_resolution.status_code, 200)
            reputation_resolution_payload = reputation_resolution.json()
            self.assertEqual(
                reputation_resolution_payload["type"],
                "https://github.com/akoita/proof-of-audit#reputation-resolution-v1",
            )
            self.assertTrue(reputation_resolution_payload["claimConfirmed"])

            reputation_summary = client.get("/auditor/reputation")
            self.assertEqual(reputation_summary.status_code, 200)
            self.assertEqual(reputation_summary.json()["reputation"]["score"], 100)

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

        comparison = self.client.get(
            "/targets/0x1000000000000000000000000000000000000001/comparison"
        )
        self.assertEqual(comparison.status_code, 200)
        comparison_payload = comparison.json()
        self.assertEqual(comparison_payload["summary"]["claim_count"], 2)
        self.assertEqual(comparison_payload["summary"]["published_count"], 0)
        self.assertEqual(comparison_payload["summary"]["challenged_count"], 0)
        self.assertEqual(comparison_payload["summary"]["resolved_count"], 0)


class AuditApiAgentForgeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.data_root = self.root / "data"
        self.data_root.mkdir()
        self.fixtures_file = self.root / "demo-fixtures.localhost.json"
        self.fixtures_file.write_text(json.dumps({"fixtures": []}) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _create_client(
        self,
        *,
        mode: str,
        command: Path | None,
        runs_home: Path,
        service_url: str | None = None,
    ) -> TestClient:
        name = command.name if command is not None else "service"
        env_file = self.root / f".env.{mode}.{name}"
        lines = [
            f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={self.fixtures_file}",
            f"PROOF_OF_AUDIT_WORKER_RUNTIME_MODE={mode}",
            f"PROOF_OF_AUDIT_AGENT_FORGE_RUNS_HOME={runs_home}",
        ]
        if command is not None:
            lines.append(f"PROOF_OF_AUDIT_AGENT_FORGE_COMMAND={command}")
        if service_url is not None:
            lines.extend(
                [
                    f"PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_URL={service_url}",
                    "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_POLL_INTERVAL_SECONDS=0",
                ]
            )
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return TestClient(create_app(self.data_root, env_file=env_file))

    def test_repository_submission_hybrid_persists_live_execution_metadata(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        (repo_dir / "Vault.sol").write_text("contract Vault {}\n", encoding="utf-8")
        runs_home = self.root / "home-success"
        script = write_fake_agent_forge_script(
            self.root / "agent-forge-success",
            report_payload={
                "benchmark_id": "agent-forge-live",
                "summary": "Live repository audit completed.",
                "confidence": "medium",
                "findings": [
                    {
                        "title": "Reentrancy in withdraw()",
                        "severity": "high",
                        "category": "reentrancy",
                        "description": "External call happens before state update.",
                        "impact": "Funds can be drained recursively.",
                        "recommendation": "Apply checks-effects-interactions.",
                        "confidence": "medium",
                        "source_path": "Vault.sol",
                        "detector": "agent_forge.live",
                    }
                ],
            },
        )
        client = self._create_client(mode="hybrid", command=script, runs_home=runs_home)

        response = client.post(
            "/audits",
            json={
                "input_kind": "repository_url",
                "repository_url": str(repo_dir),
                "entry_contract": "Vault",
                "submitted_by": "repo-test",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["submission"]["input_kind"], "repository_url")
        self.assertEqual(payload["execution"]["backend"], "agent_forge")
        self.assertEqual(payload["execution"]["status"], "completed")
        self.assertEqual(payload["execution"]["run_id"], "run-123")
        self.assertFalse(payload["execution"]["fallback_used"])
        self.assertEqual(payload["report"]["benchmark_id"], "agent-forge-live")
        self.assertEqual(payload["report"]["finding_count"], 1)

    def test_repository_submission_hybrid_falls_back_when_agent_forge_fails(self) -> None:
        repo_dir = self.root / "repo-fallback"
        repo_dir.mkdir()
        (repo_dir / "Vault.sol").write_text("contract Vault {}\n", encoding="utf-8")
        runs_home = self.root / "home-fallback"
        script = write_fake_agent_forge_script(
            self.root / "agent-forge-fail",
            report_payload=None,
            exit_code=2,
            stderr_text="boom",
        )
        client = self._create_client(mode="hybrid", command=script, runs_home=runs_home)

        response = client.post(
            "/audits",
            json={
                "input_kind": "repository_url",
                "repository_url": str(repo_dir),
                "entry_contract": "Vault",
                "submitted_by": "repo-test",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["execution"]["status"], "fallback")
        self.assertTrue(payload["execution"]["fallback_used"])
        self.assertEqual(payload["report"]["benchmark_id"], "repository-url")

    def test_source_bundle_submission_hybrid_extracts_zip_and_runs_live_backend(self) -> None:
        bundle_path = self.root / "source-bundle.zip"
        with zipfile.ZipFile(bundle_path, "w") as archive:
            archive.writestr("wrapped/src/Vault.sol", "contract Vault {}\n")
        runs_home = self.root / "home-bundle"
        script = write_fake_agent_forge_script(
            self.root / "agent-forge-bundle",
            report_payload={
                "benchmark_id": "agent-forge-live",
                "summary": "Live bundle audit completed.",
                "confidence": "medium",
                "findings": [
                    {
                        "title": "Unchecked external call",
                        "severity": "medium",
                        "category": "unchecked_external_call",
                        "description": "Low-level call return value ignored.",
                        "impact": "Failures may be swallowed.",
                        "recommendation": "Check the returned boolean.",
                        "source_path": "src/Vault.sol",
                    }
                ],
            },
        )
        client = self._create_client(mode="hybrid", command=script, runs_home=runs_home)

        response = client.post(
            "/audits",
            json={
                "input_kind": "source_bundle",
                "source_bundle_uri": str(bundle_path),
                "entry_contract": "Vault",
                "submitted_by": "bundle-test",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["submission"]["input_kind"], "source_bundle")
        self.assertEqual(payload["execution"]["backend"], "agent_forge")
        self.assertEqual(payload["execution"]["status"], "completed")
        self.assertEqual(payload["report"]["benchmark_id"], "agent-forge-live")
        self.assertEqual(payload["report"]["findings"][0]["source_path"], "src/Vault.sol")

    def test_source_bundle_submission_hybrid_accepts_single_sol_file(self) -> None:
        bundle_path = self.root / "UncheckedTreasury.sol"
        bundle_path.write_text("contract UncheckedTreasury {}\n", encoding="utf-8")
        runs_home = self.root / "home-sol"
        script = write_fake_agent_forge_script(
            self.root / "agent-forge-sol",
            report_payload={
                "benchmark_id": "agent-forge-live-sol",
                "summary": "Live Solidity file audit completed.",
                "confidence": "medium",
                "findings": [
                    {
                        "title": "Unchecked external call",
                        "severity": "medium",
                        "category": "unchecked_external_call",
                        "description": "Low-level call return value ignored.",
                        "impact": "Failures may be swallowed.",
                        "recommendation": "Check the returned boolean.",
                        "source_path": "UncheckedTreasury.sol",
                    }
                ],
            },
        )
        client = self._create_client(mode="hybrid", command=script, runs_home=runs_home)

        response = client.post(
            "/audits",
            json={
                "input_kind": "source_bundle",
                "source_bundle_uri": str(bundle_path),
                "entry_contract": "UncheckedTreasury",
                "submitted_by": "bundle-test",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["submission"]["input_kind"], "source_bundle")
        self.assertEqual(payload["execution"]["backend"], "agent_forge")
        self.assertEqual(payload["execution"]["status"], "completed")
        self.assertEqual(payload["report"]["benchmark_id"], "agent-forge-live-sol")
        self.assertEqual(
            payload["report"]["findings"][0]["source_path"],
            "UncheckedTreasury.sol",
        )

    def test_deployed_address_submission_hybrid_runs_live_verified_source_path(self) -> None:
        runs_home = self.root / "home-deployed"
        script = write_fake_agent_forge_script(
            self.root / "agent-forge-deployed",
            report_payload={
                "benchmark_id": "agent-forge-live",
                "summary": "Live deployed-address audit completed.",
                "confidence": "medium",
                "findings": [
                    {
                        "title": "Unchecked external call",
                        "severity": "medium",
                        "category": "unchecked_external_call",
                        "description": "Low-level call return value ignored.",
                        "impact": "Failures may be swallowed.",
                        "recommendation": "Check the returned boolean.",
                        "source_path": "src/Vault.sol",
                    }
                ],
            },
        )
        client = self._create_client(mode="hybrid", command=script, runs_home=runs_home)
        source_tempdir = tempfile_module.TemporaryDirectory(prefix="proof-of-audit-test-")
        source_root = Path(source_tempdir.name) / "source"
        (source_root / "src").mkdir(parents=True, exist_ok=True)
        (source_root / "src" / "Vault.sol").write_text("contract Vault {}\n", encoding="utf-8")

        with patch(
            "proof_of_audit_agent.agent_forge_backend.DeployedAddressSourceResolver.resolve",
            return_value=type(
                "ResolvedSource",
                (),
                {
                    "path": source_root,
                    "tempdir": source_tempdir,
                    "entry_contract": "Vault",
                    "source_uri": "sourcify://84532/0xabc0000000000000000000000000000000000000",
                },
            )(),
        ):
            response = client.post(
                "/audits",
                json={
                    "input_kind": "deployed_address",
                    "chain_id": 84532,
                    "contract_address": "0xabc0000000000000000000000000000000000000",
                    "submitted_by": "deployed-test",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["submission"]["input_kind"], "deployed_address")
        self.assertEqual(payload["execution"]["backend"], "agent_forge")
        self.assertEqual(payload["execution"]["status"], "completed")
        self.assertEqual(
            payload["execution"]["source_path"],
            "sourcify://84532/0xabc0000000000000000000000000000000000000",
        )
        self.assertEqual(
            payload["report"]["contract_address"],
            "0xabc0000000000000000000000000000000000000",
        )

    def test_deployed_address_submission_hybrid_rejects_fake_fallback_when_live_lookup_fails(self) -> None:
        runs_home = self.root / "home-deployed-fallback"
        script = write_fake_agent_forge_script(
            self.root / "agent-forge-deployed-fallback",
            report_payload=None,
        )
        client = self._create_client(mode="hybrid", command=script, runs_home=runs_home)

        with patch(
            "proof_of_audit_agent.agent_forge_backend.DeployedAddressSourceResolver.resolve",
            side_effect=ValueError("missing verified source"),
        ):
            response = client.post(
                "/audits",
                json={
                    "input_kind": "deployed_address",
                    "chain_id": 84532,
                    "contract_address": "0xabc0000000000000000000000000000000000000",
                    "submitted_by": "deployed-test",
                },
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"], "invalid_payload")
        self.assertIn("require live agent-forge analysis", payload["message"])

    def test_deployed_address_submission_hybrid_rejects_fixture_benchmark_fallbacks(self) -> None:
        self.fixtures_file.write_text(
            json.dumps(
                {
                    "fixtures": [
                        {
                            "id": "vulnerable-bank",
                            "label": "Vulnerable Bank",
                            "contract_name": "VulnerableBank",
                            "entry_contract": "VulnerableBank",
                            "benchmark_id": "reentrancy-bank",
                            "address": "0xEbB43aa379270bcBbffDf33656AC37eBD7C81A11",
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
        runs_home = self.root / "home-deployed-fixture"
        script = write_fake_agent_forge_script(
            self.root / "agent-forge-deployed-fixture",
            report_payload=None,
        )
        client = self._create_client(mode="hybrid", command=script, runs_home=runs_home)

        with patch(
            "proof_of_audit_agent.agent_forge_backend.DeployedAddressSourceResolver.resolve",
            side_effect=ValueError("missing verified source"),
        ):
            response = client.post(
                "/audits",
                json={
                    "input_kind": "deployed_address",
                    "chain_id": 84532,
                    "contract_address": "0xEbB43aa379270bcBbffDf33656AC37eBD7C81A11",
                    "submitted_by": "deployed-test",
                },
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"], "invalid_payload")
        self.assertIn("require live agent-forge analysis", payload["message"])

    def test_deployed_address_submission_trims_fixture_address_whitespace_for_live_execution(self) -> None:
        self.fixtures_file.write_text(
            json.dumps(
                {
                    "fixtures": [
                        {
                            "id": "vulnerable-bank",
                            "label": "Vulnerable Bank",
                            "contract_name": "VulnerableBank",
                            "entry_contract": "VulnerableBank",
                            "benchmark_id": "reentrancy-bank",
                            "address": "0xEbB43aa379270bcBbffDf33656AC37eBD7C81A11",
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
        runs_home = self.root / "home-deployed-fixture-trimmed"
        script = write_fake_agent_forge_script(
            self.root / "agent-forge-deployed-fixture-trimmed",
            report_payload={
                "benchmark_id": "agent-forge-live",
                "summary": "Live deployed-address audit completed.",
                "confidence": "medium",
                "findings": [
                    {
                        "title": "Potential reentrancy after external call",
                        "severity": "high",
                        "category": "reentrancy",
                        "description": "External interaction occurs before balance state is updated.",
                        "impact": "A malicious callee can re-enter before balances are reduced.",
                        "recommendation": "Apply checks-effects-interactions.",
                        "source_path": "src/VulnerableBank.sol",
                    }
                ],
            },
        )
        client = self._create_client(mode="hybrid", command=script, runs_home=runs_home)
        source_tempdir = tempfile_module.TemporaryDirectory(prefix="proof-of-audit-test-")
        source_root = Path(source_tempdir.name) / "source"
        (source_root / "src").mkdir(parents=True, exist_ok=True)
        (source_root / "src" / "VulnerableBank.sol").write_text(
            "contract VulnerableBank {}\n",
            encoding="utf-8",
        )

        with patch(
            "proof_of_audit_agent.agent_forge_backend.DeployedAddressSourceResolver.resolve",
            return_value=type(
                "ResolvedSource",
                (),
                {
                    "path": source_root,
                    "tempdir": source_tempdir,
                    "entry_contract": "VulnerableBank",
                    "source_uri": "explorer://84532/0xebb43aa379270bcbbffdf33656ac37ebd7c81a11",
                },
            )(),
        ):
            response = client.post(
                "/audits",
                json={
                    "input_kind": "deployed_address",
                    "chain_id": 84532,
                    "contract_address": " 0xEbB43aa379270bcBbffDf33656AC37eBD7C81A11 ",
                    "submitted_by": "deployed-test",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(
            payload["contract_address"],
            "0xebb43aa379270bcbbffdf33656ac37ebd7c81a11",
        )
        self.assertEqual(payload["execution"]["backend"], "agent_forge")
        self.assertEqual(payload["execution"]["status"], "completed")
        self.assertEqual(payload["report"]["benchmark_id"], "agent-forge-live")
        self.assertEqual(payload["report"]["finding_count"], 1)

    def test_deployed_address_submission_hybrid_uses_hosted_agent_forge_service(self) -> None:
        runs_home = self.root / "home-deployed-service"
        client = self._create_client(
            mode="hybrid",
            command=None,
            runs_home=runs_home,
            service_url="http://agent-forge.test",
        )
        source_tempdir = tempfile_module.TemporaryDirectory(prefix="proof-of-audit-test-service-")
        source_root = Path(source_tempdir.name) / "source"
        (source_root / "src").mkdir(parents=True, exist_ok=True)
        (source_root / "src" / "Vault.sol").write_text("contract Vault {}\n", encoding="utf-8")
        captured_requests: list[dict[str, object]] = []
        fake_client = FakeHostedHttpClient(
            responses=[
                {
                    "status_code": 202,
                    "json": {
                        "schema_version": "agent-forge-run-v1",
                        "run_id": "run_service_123",
                        "status": "accepted",
                        "status_url": "/v1/runs/run_service_123",
                        "report_url": "/v1/runs/run_service_123/report",
                        "logs_url": "/v1/runs/run_service_123/logs",
                        "created_at": "2026-03-25T10:30:00Z",
                    },
                },
                {
                    "status_code": 200,
                    "json": {
                        "schema_version": "agent-forge-run-v1",
                        "run_id": "run_service_123",
                        "status": "completed",
                        "status_url": "/v1/runs/run_service_123",
                        "report_url": "/v1/runs/run_service_123/report",
                        "logs_url": "/v1/runs/run_service_123/logs",
                        "created_at": "2026-03-25T10:30:00Z",
                        "completed_at": "2026-03-25T10:30:06Z",
                    },
                },
                {
                    "status_code": 200,
                    "json": {
                        "schema_version": "proof-of-audit-report-v1",
                        "run_id": "run_service_123",
                        "summary": "Hosted service completed a live deployed-address review.",
                        "confidence": "medium",
                        "benchmark_id": "agent-forge-service-live",
                        "target": {
                            "submission_kind": "deployed_address",
                            "network": "base-sepolia",
                            "chain_id": 84532,
                            "contract_address": "0xabc0000000000000000000000000000000000000",
                            "entry_contract": "Vault",
                        },
                        "findings": [
                            {
                                "finding_id": "finding-1",
                                "title": "Unchecked external call",
                                "severity": "medium",
                                "category": "unchecked_external_call",
                                "description": "Return value ignored.",
                                "impact": "Silent failure may mask execution problems.",
                                "recommendation": "Check the returned boolean.",
                                "confidence": "medium",
                                "detector": "agent_forge.service.unchecked_call",
                                "source_path": "src/Vault.sol",
                            }
                        ],
                        "stats": {
                            "finding_count": 1,
                            "max_severity": "medium",
                            "severity_breakdown": {
                                "critical": 0,
                                "high": 0,
                                "medium": 1,
                                "low": 0,
                            },
                        },
                        "provenance": {
                            "profile_id": "proof-of-audit-solidity-v1",
                            "source_digest": "sha256:placeholder",
                        },
                    },
                },
                {
                    "status_code": 200,
                    "json": {
                        "run_id": "run_service_123",
                        "artifacts": {
                            "run_dir": "/tmp/agent-forge/runs/run_service_123",
                        },
                    },
                },
            ],
            requests=captured_requests,
        )
        uploaded_archives: list[tuple[str, Path]] = []

        def fake_store_service_source_archive(
            _: object,
            audit_id: str,
            archive_path: Path,
        ) -> str:
            uploaded_archives.append((audit_id, archive_path))
            return "gs://proof-of-audit-source-bundles/run_service_123.zip"

        with (
            patch(
                "proof_of_audit_agent.agent_forge_backend.DeployedAddressSourceResolver.resolve",
                return_value=type(
                    "ResolvedSource",
                    (),
                    {
                        "path": source_root,
                        "tempdir": source_tempdir,
                        "entry_contract": "Vault",
                        "source_uri": "sourcify://84532/0xabc0000000000000000000000000000000000000",
                    },
                )(),
            ),
            patch(
                "proof_of_audit_agent.agent_forge_service_client.httpx.Client",
                return_value=fake_client,
            ),
            patch(
                "proof_of_audit_agent.agent_forge_backend.AgentForgeBackend._store_service_source_archive",
                autospec=True,
                side_effect=fake_store_service_source_archive,
            ),
        ):
            response = client.post(
                "/audits",
                json={
                    "input_kind": "deployed_address",
                    "chain_id": 84532,
                    "contract_address": "0xabc0000000000000000000000000000000000000",
                    "submitted_by": "deployed-service-test",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["execution"]["backend"], "agent_forge")
        self.assertEqual(payload["execution"]["source"], "agent_forge_service")
        self.assertEqual(
            payload["execution"]["status_url"],
            "http://agent-forge.test/v1/runs/run_service_123",
        )
        self.assertEqual(
            payload["execution"]["report_path"],
            "http://agent-forge.test/v1/runs/run_service_123/report",
        )
        self.assertEqual(payload["report"]["benchmark_id"], "agent-forge-service-live")
        self.assertEqual(payload["report"]["finding_count"], 1)
        self.assertEqual(
            payload["report"]["contract_address"],
            "0xabc0000000000000000000000000000000000000",
        )

        create_run_request = captured_requests[0]
        request_payload = create_run_request["json"]
        assert isinstance(request_payload, dict)
        self.assertEqual(request_payload["target"]["submission_kind"], "deployed_address")
        self.assertEqual(request_payload["target"]["network"], "base-sepolia")
        self.assertEqual(
            request_payload["source"]["uri"],
            "gs://proof-of-audit-source-bundles/run_service_123.zip",
        )
        self.assertTrue(uploaded_archives)
        _, archive_path = uploaded_archives[0]
        self.assertTrue(archive_path.exists())
        with zipfile.ZipFile(archive_path) as archive:
            self.assertIn("src/Vault.sol", archive.namelist())


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
        self.assertEqual(
            payload["report"]["normalized_findings"][0]["schema_version"],
            "normalized-audit-finding/v1",
        )
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
        self.assertEqual(challenge_payload["status"], "challenged")
        self.assertEqual(challenge_payload["challenge"]["status"], "opened")
        self.assertIsNone(challenge_payload["challenge"].get("resolution"))
        self.assertEqual(
            challenge_payload["challenge"]["verification_status"],
            "verifier_unavailable",
        )
        self.assertEqual(
            challenge_payload["challenge"]["resolution_path"],
            "manual_fallback",
        )
        self.assertEqual(
            challenge_payload["challenge"]["challenger_address"],
            self.client.app.state.audit_service.publisher.account.address,
        )
        self.assertTrue(challenge_payload["challenge"]["challenge_tx_hash"].startswith("0x"))
        self.assertIsNone(challenge_payload["challenge"]["resolve_tx_hash"])

        audit_record = self.onchain.contract.functions.getAudit(1).call()
        self.assertEqual(int(audit_record[10]), 2)
        self.assertEqual(int(audit_record[11]), 0)

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
            "verifier_unavailable",
        )
        self.assertEqual(
            challenge_payload["challenge"]["resolution_path"],
            "manual_fallback",
        )

    def test_verifier_failure_after_challenge_leaves_a_recoverable_audit(self) -> None:
        class RaisingVerifier:
            def verify(self, context: EvidenceContext) -> ChallengeVerificationResult:
                raise RuntimeError("verifier crashed")

        service = AuditService(
            Path(self.tempdir.name) / "verifier-failure-data",
            contract_config=self.onchain.contract_config,
            publisher=self.onchain.publisher,
            arbiter_client=self.onchain.arbiter_client,
            challenge_verifiers={
                "deterministic_fixture": RaisingVerifier(),
            },
        )
        failing_client = TestClient(
            create_app(audit_service=service),
            raise_server_exceptions=False,
        )

        created = failing_client.post(
            "/audits",
            json={
                "contract_address": self.target_address,
                "submitted_by": "integration-test",
            },
        )
        self.assertEqual(created.status_code, 201)
        audit_id = created.json()["id"]

        published = failing_client.post(
            f"/audits/{audit_id}/publish",
            json={"stake_wei": 10**16},
        )
        self.assertEqual(published.status_code, 200)

        challenged = failing_client.post(
            f"/audits/{audit_id}/challenge",
            json={
                "proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
                "challenger": "whitehat-demo",
            },
        )
        self.assertEqual(challenged.status_code, 500)

        fetched = failing_client.get(f"/audits/{audit_id}")
        self.assertEqual(fetched.status_code, 200)
        payload = fetched.json()
        self.assertEqual(payload["status"], "challenged")
        self.assertEqual(payload["challenge"]["status"], "opened")
        self.assertEqual(payload["challenge"]["verification_status"], "pending")
        self.assertTrue(payload["challenge"]["challenge_tx_hash"].startswith("0x"))

        audit_record = self.onchain.contract.functions.getAudit(1).call()
        self.assertEqual(int(audit_record[10]), 2)
        self.assertEqual(int(audit_record[11]), 0)

        resolved = failing_client.post(
            f"/audits/{audit_id}/resolve",
            json={"upheld": True, "resolved_by": "integration-arbiter"},
        )
        self.assertEqual(resolved.status_code, 200)
        resolved_payload = resolved.json()
        self.assertEqual(resolved_payload["status"], "resolved")
        self.assertEqual(resolved_payload["challenge"]["status"], "upheld")
        self.assertEqual(
            resolved_payload["challenge"]["resolution_path"],
            "manual_fallback",
        )
        self.assertTrue(resolved_payload["challenge"]["resolve_tx_hash"].startswith("0x"))

        resolved_record = self.onchain.contract.functions.getAudit(1).call()
        self.assertEqual(int(resolved_record[10]), 3)
        self.assertEqual(int(resolved_record[11]), 1)

    def test_typed_executable_challenge_round_trips_through_api(self) -> None:
        class RecordingVerifier:
            def __init__(self) -> None:
                self.last_context: EvidenceContext | None = None

            def verify(self, context: EvidenceContext) -> ChallengeVerificationResult:
                self.last_context = context
                return ChallengeVerificationResult(
                    verifier="executable-evidence-advisory-v1",
                    status="verified",
                    summary="advisory rejected",
                    detail="already reported",
                    resolution="rejected",
                    advisory_only=True,
                    execution_log="forge output",
                    matched_findings=["finding-1"],
                    unmatched_findings=[],
                )

        recording_verifier = RecordingVerifier()
        service = AuditService(
            Path(self.tempdir.name) / "typed-data",
            contract_config=self.onchain.contract_config,
            publisher=self.onchain.publisher,
            arbiter_client=self.onchain.arbiter_client,
            challenge_verifiers={
                "deterministic_fixture": self.client.app.state.audit_service.challenge_verifiers["deterministic_fixture"],
                "executable_test": recording_verifier,
            },
        )
        typed_client = TestClient(create_app(audit_service=service))

        created = typed_client.post(
            "/audits",
            json={
                "contract_address": self.target_address,
                "submitted_by": "integration-test",
            },
        )
        self.assertEqual(created.status_code, 201)
        audit_id = created.json()["id"]
        evidence_path = Path(self.tempdir.name) / "ChallengeEvidence.t.sol"
        evidence_path.write_text(
            "contract ChallengeEvidenceTest {}\n",
            encoding="utf-8",
        )
        published = typed_client.post(
            f"/audits/{audit_id}/publish",
            json={"stake_wei": 10**16},
        )
        self.assertEqual(published.status_code, 200)

        challenged = typed_client.post(
            f"/audits/{audit_id}/challenge",
            json={
                "proof_uri": evidence_path.as_uri(),
                "evidence_type": "executable_test",
                "evidence_manifest": {
                    "bundle_format": "proof-of-audit-executable-evidence/v1",
                    "execution_env": "foundry",
                    "entrypoint": "ChallengeEvidence.t.sol",
                    "target_chain_id": self.chain_id,
                    "pinned_block_number": 42,
                },
                "challenger": "whitehat-demo",
            },
        )
        self.assertEqual(challenged.status_code, 200)
        payload = challenged.json()
        self.assertEqual(payload["status"], "challenged")
        self.assertEqual(payload["challenge"]["evidence_type"], "executable_test")
        self.assertEqual(payload["challenge"]["execution_env"], "foundry")
        self.assertEqual(
            payload["challenge"]["evidence_manifest"]["entrypoint"],
            "ChallengeEvidence.t.sol",
        )
        self.assertTrue(payload["challenge"]["evidence_hash"].startswith("0x"))
        self.assertEqual(
            payload["challenge"]["challenge_hash"],
            payload["challenge"]["evidence_hash"],
        )
        self.assertEqual(payload["challenge"]["advisory_verdict"], "rejected")
        self.assertEqual(payload["challenge"]["execution_log"], "forge output")
        self.assertEqual(payload["challenge"]["matched_findings"], ["finding-1"])
        self.assertEqual(
            payload["challenge"]["verification_dossier_path"],
            f"/audits/{audit_id}/challenge/dossier",
        )
        self.assertEqual(
            payload["challenge"]["verification_dossier"]["policy"]["status"],
            "rejected",
        )
        self.assertEqual(
            payload["challenge"]["verification_dossier"]["comparison"]["status"],
            "already_covered",
        )
        self.assertGreaterEqual(
            len(payload["challenge"]["verification_dossier"]["comparison"]["matched_findings"]),
            1,
        )
        self.assertEqual(
            payload["challenge"]["verification_dossier"]["execution"]["execution_env"],
            "foundry",
        )

        fetched = typed_client.get(f"/audits/{audit_id}")
        self.assertEqual(fetched.status_code, 200)
        fetched_payload = fetched.json()
        self.assertEqual(fetched_payload["challenge"]["evidence_type"], "executable_test")
        self.assertEqual(fetched_payload["challenge"]["execution_env"], "foundry")
        self.assertEqual(
            fetched_payload["challenge"]["evidence_manifest"]["pinned_block_number"],
            42,
        )
        self.assertEqual(
            fetched_payload["challenge"]["verification_dossier"]["comparison"]["matched_finding_ids"],
            ["finding-1"],
        )
        self.assertIsNotNone(recording_verifier.last_context)
        self.assertEqual(recording_verifier.last_context.evidence_type, "executable_test")
        self.assertEqual(recording_verifier.last_context.evidence_manifest["target_chain_id"], self.chain_id)
        self.assertEqual(
            recording_verifier.last_context.committed_evidence_hash,
            payload["challenge"]["evidence_hash"],
        )

    def test_deterministic_evidence_rejects_execution_env_payload(self) -> None:
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

        challenged = self.client.post(
            f"/audits/{audit_id}/challenge",
            json={
                "proof_uri": "ipfs://wrong-proof",
                "execution_env": "foundry",
                "challenger": "whitehat-demo",
            },
        )
        self.assertEqual(challenged.status_code, 422)
        self.assertEqual(challenged.json()["error"], "validation_error")

    def test_deterministic_evidence_rejects_manifest_payload(self) -> None:
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

        challenged = self.client.post(
            f"/audits/{audit_id}/challenge",
            json={
                "proof_uri": "ipfs://wrong-proof",
                "evidence_manifest": {
                    "bundle_format": "proof-of-audit-executable-evidence/v1",
                    "execution_env": "foundry",
                    "entrypoint": "ChallengeEvidence.t.sol",
                    "target_chain_id": self.chain_id,
                },
                "challenger": "whitehat-demo",
            },
        )
        self.assertEqual(challenged.status_code, 422)
        self.assertEqual(challenged.json()["error"], "validation_error")
