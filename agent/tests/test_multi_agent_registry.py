"""Tests for multi-agent registry support (issue #274).

Validates:
- Catalog generation from demo/agents.json
- Per-agent runtime override resolution
- Worker runtime_overrides parameter
- Backwards compatibility for single-agent deployments
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def agents_manifest(tmp_path: Path) -> Path:
    manifest = {
        "schema_version": "agent-personas/v1",
        "agents": [
            {
                "service_id": "agent-reentrancy-hawk",
                "name": "Reentrancy Hawk",
                "description": "Specialist agent focused on reentrancy.",
                "profile": "reentrancy-specialist",
                "runtime_mode": "hybrid",
                "capabilities": ["audit_contract"],
                "detectors": ["reentrancy"],
                "challenge_strategy": "silent-monitor",
                "identity": {"agent_id": 1, "operator": "Test", "anvil_account_index": 1},
            },
            {
                "service_id": "agent-full-spectrum",
                "name": "Full Spectrum Auditor",
                "description": "Broad-coverage agent.",
                "profile": "full-spectrum-auditor",
                "runtime_mode": "hybrid",
                "capabilities": ["audit_contract", "review_challenge_evidence"],
                "detectors": ["reentrancy", "access_control", "unchecked_external_call"],
                "challenge_strategy": "auto-challenge",
                "identity": {"agent_id": 3, "operator": "Test", "anvil_account_index": 3},
            },
        ],
    }
    path = tmp_path / "agents.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


@pytest.fixture()
def catalog_output(tmp_path: Path) -> Path:
    return tmp_path / "auditor-catalog.json"


# ---------------------------------------------------------------------------
# Catalog generator import
# ---------------------------------------------------------------------------

def _import_catalog_module():
    import importlib.util
    script_path = (
        Path(__file__).resolve().parent.parent.parent
        / "scripts"
        / "generate-auditor-catalog.py"
    )
    spec = importlib.util.spec_from_file_location("gen_catalog", str(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Tests: Catalog Generation
# ---------------------------------------------------------------------------


class TestCatalogGeneration:
    def test_generates_catalog_from_manifest(
        self, agents_manifest: Path, catalog_output: Path
    ):
        mod = _import_catalog_module()
        test_args = [
            "generate-auditor-catalog.py",
            "--agents-manifest", str(agents_manifest),
            "--output", str(catalog_output),
            "--network", "anvil-local",
            "--api-base-url", "http://127.0.0.1:8080",
        ]
        with patch.object(sys, "argv", test_args):
            result = mod.main()

        assert result == 0
        assert catalog_output.exists()

        catalog = json.loads(catalog_output.read_text(encoding="utf-8"))
        assert catalog["schema_version"] == "auditor-catalog/v1"
        assert catalog["network"] == "anvil-local"
        assert catalog["item_count"] == 2

    def test_each_entry_has_service_and_registration(
        self, agents_manifest: Path, catalog_output: Path
    ):
        mod = _import_catalog_module()
        test_args = [
            "script",
            "--agents-manifest", str(agents_manifest),
            "--output", str(catalog_output),
        ]
        with patch.object(sys, "argv", test_args):
            mod.main()

        catalog = json.loads(catalog_output.read_text(encoding="utf-8"))
        for item in catalog["items"]:
            assert "service" in item
            assert "registration_document" in item

            svc = item["service"]
            assert svc["service_id"]
            assert svc["name"]
            assert svc["execution_mode"] == "local_worker"
            assert svc["active"] is True
            assert "detectors" in svc
            assert "profile_id" in svc
            assert "submission_modes" in svc

    def test_registration_document_has_detectors(
        self, agents_manifest: Path, catalog_output: Path
    ):
        mod = _import_catalog_module()
        test_args = [
            "script",
            "--agents-manifest", str(agents_manifest),
            "--output", str(catalog_output),
        ]
        with patch.object(sys, "argv", test_args):
            mod.main()

        catalog = json.loads(catalog_output.read_text(encoding="utf-8"))
        hawk = next(
            i for i in catalog["items"]
            if i["service"]["service_id"] == "agent-reentrancy-hawk"
        )
        assert hawk["registration_document"]["detectors"] == ["reentrancy"]
        assert hawk["registration_document"]["profile"] == "reentrancy-specialist"

    def test_missing_manifest_returns_error(self, catalog_output: Path):
        mod = _import_catalog_module()
        test_args = [
            "script",
            "--agents-manifest", "/nonexistent/agents.json",
            "--output", str(catalog_output),
        ]
        with patch.object(sys, "argv", test_args):
            result = mod.main()
        assert result == 1

    def test_exclude_primary(
        self, tmp_path: Path, catalog_output: Path
    ):
        manifest = {
            "schema_version": "agent-personas/v1",
            "agents": [
                {
                    "service_id": "proof-of-audit-auditor",
                    "name": "Primary",
                    "profile": "default",
                    "runtime_mode": "hybrid",
                    "capabilities": ["audit_contract"],
                    "detectors": ["*"],
                    "identity": {"agent_id": 0, "operator": "Test", "anvil_account_index": 0},
                },
                {
                    "service_id": "agent-hawk",
                    "name": "Hawk",
                    "profile": "reentrancy",
                    "runtime_mode": "hybrid",
                    "capabilities": ["audit_contract"],
                    "detectors": ["reentrancy"],
                    "identity": {"agent_id": 1, "operator": "Test", "anvil_account_index": 1},
                },
            ],
        }
        manifest_path = tmp_path / "agents.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        mod = _import_catalog_module()
        test_args = [
            "script",
            "--agents-manifest", str(manifest_path),
            "--output", str(catalog_output),
            "--exclude-primary",
        ]
        with patch.object(sys, "argv", test_args):
            result = mod.main()

        assert result == 0
        catalog = json.loads(catalog_output.read_text(encoding="utf-8"))
        assert catalog["item_count"] == 1
        assert catalog["items"][0]["service"]["service_id"] == "agent-hawk"


# ---------------------------------------------------------------------------
# Tests: Worker Runtime Overrides
# ---------------------------------------------------------------------------


class TestWorkerRuntimeOverrides:
    @staticmethod
    def _worker_with_fixture():
        """Create an AuditWorker with a minimal test fixture injected."""
        from proof_of_audit_agent.worker import AuditWorker
        from proof_of_audit_agent.fixtures import DemoFixture

        worker = AuditWorker()
        # Inject a test fixture so the deterministic backend can resolve it
        # even without deployments/demo-fixtures.localhost.json present.
        test_fixture = DemoFixture(
            fixture_id="vulnerable-bank",
            label="Vulnerable Bank",
            contract_name="VulnerableBank",
            entry_contract="VulnerableBank",
            benchmark_id="reentrancy-bank",
            address="0x0000000000000000000000000000000000001111",
            challenge_proof_uri="ipfs://test",
            note="test fixture",
            source_path="demo/contracts/VulnerableBank.sol",
        )
        worker.deterministic_backend._fixtures_by_id["vulnerable-bank"] = test_fixture
        return worker

    def test_run_submission_without_overrides(self):
        """Single-agent backward compat: no overrides = same behavior."""
        worker = self._worker_with_fixture()
        result = worker.run_submission(
            input_kind="demo_fixture",
            fixture_id="vulnerable-bank",
            runtime_overrides=None,
        )
        assert result is not None
        assert result.report is not None

    def test_run_submission_with_detector_overrides(self):
        """Per-agent overrides should be applied and restored."""
        worker = self._worker_with_fixture()
        original_detectors = worker.agent_forge.runtime.detectors

        overrides = {"detectors": ["reentrancy"], "audit_profile": "hawk-profile"}
        result = worker.run_submission(
            input_kind="demo_fixture",
            fixture_id="vulnerable-bank",
            runtime_overrides=overrides,
        )
        assert result is not None

        # Verify original config is restored after execution
        assert worker.agent_forge.runtime.detectors == original_detectors

    def test_apply_runtime_overrides(self):
        from proof_of_audit_agent.worker import AuditWorker

        worker = AuditWorker()
        base = worker.agent_forge.runtime

        overrides = {"detectors": ["access_control"], "audit_profile": "sentinel"}
        new_config = worker._apply_runtime_overrides(base, overrides)

        assert new_config.detectors == ("access_control",)
        assert new_config.audit_profile == "sentinel"
        # Base config should be unchanged
        assert base.detectors != ("access_control",) or base.detectors is None

    def test_apply_runtime_overrides_ignores_none_values(self):
        from proof_of_audit_agent.worker import AuditWorker

        worker = AuditWorker()
        base = worker.agent_forge.runtime

        overrides = {"detectors": None, "audit_profile": None}
        new_config = worker._apply_runtime_overrides(base, overrides)

        # Should keep original values
        assert new_config.detectors == base.detectors
        assert new_config.audit_profile == base.audit_profile


# ---------------------------------------------------------------------------
# Tests: Service Runtime Override Resolution
# ---------------------------------------------------------------------------


class TestServiceRuntimeOverrides:
    def test_primary_service_returns_none(self):
        """Primary auditor service should not have overrides."""
        from proof_of_audit_api.service import AuditService

        service = AuditService(
            data_root=Path("/tmp/test-multi-agent"),
        )
        result = service._resolve_service_runtime_overrides(
            service.contract_config.auditor_service.service_id
        )
        assert result is None

    def test_unknown_service_returns_none(self):
        from proof_of_audit_api.service import AuditService

        service = AuditService(
            data_root=Path("/tmp/test-multi-agent"),
        )
        result = service._resolve_service_runtime_overrides("nonexistent-service")
        assert result is None

    def test_catalog_entry_with_detectors(self, tmp_path: Path):
        """When a catalog entry has detectors, they should be returned as overrides."""
        catalog = {
            "items": [
                {
                    "service": _build_minimal_service("agent-hawk"),
                    "registration_document": {
                        "detectors": ["reentrancy"],
                        "profile": "hawk-profile",
                    },
                }
            ]
        }
        catalog_file = tmp_path / "catalog.json"
        catalog_file.write_text(json.dumps(catalog), encoding="utf-8")

        import os
        os.environ["PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE"] = str(catalog_file)
        try:
            from proof_of_audit_api.service import AuditService

            service = AuditService(data_root=tmp_path / "data")
            overrides = service._resolve_service_runtime_overrides("agent-hawk")
            assert overrides is not None
            assert overrides["detectors"] == ["reentrancy"]
            assert overrides["audit_profile"] == "hawk-profile"
        finally:
            del os.environ["PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE"]

    def test_catalog_entry_without_metadata(self, tmp_path: Path):
        """Catalog entry without detectors/profile returns None."""
        catalog = {
            "items": [
                {
                    "service": _build_minimal_service("agent-plain"),
                    "registration_document": {
                        "name": "Plain Agent",
                    },
                }
            ]
        }
        catalog_file = tmp_path / "catalog.json"
        catalog_file.write_text(json.dumps(catalog), encoding="utf-8")

        import os
        os.environ["PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE"] = str(catalog_file)
        try:
            from proof_of_audit_api.service import AuditService

            service = AuditService(data_root=tmp_path / "data")
            overrides = service._resolve_service_runtime_overrides("agent-plain")
            assert overrides is None
        finally:
            del os.environ["PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE"]


# ---------------------------------------------------------------------------
# Tests: API Routing
# ---------------------------------------------------------------------------


class TestAPIRouting:
    def test_audit_submission_schema_accepts_service_id(self):
        """The CreateAuditRequest schema already accepts service_id."""
        from proof_of_audit_api.schemas import CreateAuditRequest

        req = CreateAuditRequest(
            input_kind="deployed_address",
            contract_address="0x1234567890abcdef1234567890abcdef12345678",
            service_id="agent-hawk",
        )
        assert req.service_id == "agent-hawk"

    def test_audit_submission_schema_service_id_optional(self):
        from proof_of_audit_api.schemas import CreateAuditRequest

        req = CreateAuditRequest(
            input_kind="deployed_address",
            contract_address="0x1234567890abcdef1234567890abcdef12345678",
        )
        assert req.service_id is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_minimal_service(service_id: str) -> dict[str, Any]:
    """Build a minimal service record payload that passes AuditorServiceRecord.from_payload."""
    return {
        "service_id": service_id,
        "name": f"Test Agent {service_id}",
        "manifest_schema": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        "manifest_hash": "aabbccdd",
        "registration_kind": "eip-8004",
        "registration_type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        "registration_endpoint": f"http://localhost/auditors/{service_id}/registration",
        "registration_uri": f"http://localhost/registrations/{service_id}.json",
        "capability": "audit_contract",
        "discovery_path": f"/auditors/{service_id}",
        "submit_path": "/audits",
        "execution_mode": "local_worker",
        "publish_path_template": "/audits/{audit_id}/publish",
        "challenge_path_template": "/audits/{audit_id}/challenge",
        "network": "anvil-local",
        "active": True,
        "supported_trust": ["stake_backed"],
        "settlement_mode": "contract",
        "publication_mode": "api_then_chain",
        "staking_adapter_kind": "contract",
        "publication_scope": "full",
        "validation_request_path_template": "/audits/{audit_id}/validation/request",
        "validation_response_path_template": "/audits/{audit_id}/validation/response",
        "reputation_path_template": f"/auditors/{service_id}/reputation",
        "submission_modes": ["demo_fixture", "deployed_address", "source_bundle"],
        "resolution_modes": ["advisory_verifier", "manual_fallback"],
        "deterministic_resolution_supported": False,
        "manual_fallback_supported": True,
    }
