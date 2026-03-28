from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from api.tests.testnet.conftest import TestnetContext


@pytest.mark.testnet_smoke
def test_base_sepolia_deployed_address_uses_hosted_agent_forge_service(
    testnet_context: TestnetContext,
) -> None:
    fixture = testnet_context.smoke_fixture
    created = testnet_context.create_audit(
        input_kind="deployed_address",
        contract_address=fixture["address"],
        submitted_by=f"testnet-agent-forge-{uuid4().hex[:8]}",
    )

    assert created["status"] == "draft"
    assert created["contract_address"].lower() == str(fixture["address"]).lower()
    assert created["execution"]["backend"] == "agent_forge"
    assert created["execution"]["status"] == "completed"
    assert created["execution"]["source"] == "agent_forge_service"
    assert created["execution"]["live_attempted"] is True
    assert created["execution"]["fallback_used"] is False
    assert created["execution"]["run_id"]
    assert created["execution"]["status_url"]
    assert created["execution"]["report_path"]
    assert created["execution"]["logs_url"]
    assert created["execution"]["source_digest"]
    assert created["execution"]["profile_id"]

    published = testnet_context.publish_audit(created["id"])
    assert published["status"] == "published"
    assert published["onchain"]["publish_tx_hash"]


@pytest.mark.testnet_smoke
def test_base_sepolia_deployed_address_missing_verified_source_fails_without_fallback(
    testnet_context: TestnetContext,
) -> None:
    request_payload = {
        "input_kind": "deployed_address",
        "contract_address": testnet_context.operator_address,
        "submitted_by": f"testnet-negative-{uuid4().hex[:8]}",
    }
    response = testnet_context.client.post("/audits", json=request_payload)
    testnet_context.record_failed_submission(
        name="missing_verified_source_requires_live_agent_forge",
        response=response,
        payload=request_payload,
    )

    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["error"] == "invalid_payload"
    assert "use live hosted agent-forge analysis" in payload["message"]
