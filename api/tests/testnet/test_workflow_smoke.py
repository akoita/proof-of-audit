from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from api.tests.testnet.conftest import TestnetContext


AUDIT_STATUS_RESOLVED = 3
CHALLENGE_RESOLUTION_UPHELD = 1


@pytest.mark.testnet_smoke
def test_base_sepolia_deterministic_workflow_resolves_onchain(
    testnet_context: TestnetContext,
) -> None:
    fixture = testnet_context.smoke_fixture
    created = testnet_context.create_audit(
        input_kind="demo_fixture",
        fixture_id=fixture["id"],
        submitted_by=f"testnet-deterministic-{uuid4().hex[:8]}",
    )
    assert created["status"] == "draft"
    assert created["report"]["benchmark_id"] == "clean-vault"

    published = testnet_context.publish_audit(created["id"])
    assert published["status"] == "published"
    assert published["onchain"]["chain_id"] == testnet_context.chain_id

    challenged = testnet_context.challenge_audit(
        created["id"],
        fixture["challenge_proof_uri"],
        challenger=f"testnet-challenger-{uuid4().hex[:6]}",
        gas_action="deterministic_challenge",
    )
    assert challenged["status"] == "resolved"
    assert challenged["challenge"]["status"] == "upheld"
    assert challenged["challenge"]["resolution_path"] == "deterministic"

    fetched = testnet_context.get_audit(created["id"])
    assert fetched["status"] == "resolved"
    assert fetched["challenge"]["resolve_tx_hash"].startswith("0x")

    validation_response = testnet_context.client.get(
        f"/audits/{created['id']}/validation/response"
    )
    assert validation_response.status_code == 200

    reputation_resolution = testnet_context.client.get(
        f"/audits/{created['id']}/reputation/resolution"
    )
    assert reputation_resolution.status_code == 200

    audit_record = testnet_context.contract.functions.getAudit(
        fetched["onchain"]["audit_id"]
    ).call()
    assert int(audit_record[10]) == AUDIT_STATUS_RESOLVED
    assert int(audit_record[11]) == CHALLENGE_RESOLUTION_UPHELD


@pytest.mark.testnet_smoke
def test_base_sepolia_manual_resolution_workflow_resolves_onchain(
    testnet_context: TestnetContext,
) -> None:
    fixture = testnet_context.smoke_fixture
    created = testnet_context.create_audit(
        input_kind="demo_fixture",
        fixture_id=fixture["id"],
        submitted_by=f"testnet-manual-{uuid4().hex[:8]}",
    )
    testnet_context.publish_audit(created["id"])

    challenged = testnet_context.challenge_audit(
        created["id"],
        f"{fixture['challenge_proof_uri']}-manual-{uuid4().hex[:6]}",
        challenger=f"manual-challenger-{uuid4().hex[:6]}",
        gas_action="manual_challenge",
    )
    assert challenged["status"] == "challenged"
    assert challenged["challenge"]["status"] == "opened"
    assert challenged["challenge"]["resolution_path"] == "manual_fallback"

    resolved = testnet_context.resolve_audit(created["id"], upheld=True)
    assert resolved["status"] == "resolved"
    assert resolved["challenge"]["status"] == "upheld"
    assert resolved["challenge"]["resolution_path"] == "manual_fallback"

    validation_response = testnet_context.client.get(
        f"/audits/{created['id']}/validation/response"
    )
    assert validation_response.status_code == 200

    reputation_resolution = testnet_context.client.get(
        f"/audits/{created['id']}/reputation/resolution"
    )
    assert reputation_resolution.status_code == 200

    audit_record = testnet_context.contract.functions.getAudit(
        resolved["onchain"]["audit_id"]
    ).call()
    assert int(audit_record[10]) == AUDIT_STATUS_RESOLVED
    assert int(audit_record[11]) == CHALLENGE_RESOLUTION_UPHELD
