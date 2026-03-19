from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from api.tests.testnet.conftest import TestnetContext


@pytest.mark.testnet_smoke
def test_executable_evidence_smoke_is_gated_and_round_trips_advisory_fields(
    testnet_context: TestnetContext,
) -> None:
    proof_uri = os.environ.get("PROOF_OF_AUDIT_TESTNET_EXECUTABLE_EVIDENCE_URI", "").strip()
    if not proof_uri:
        pytest.skip(
            "optional executable evidence smoke is disabled: PROOF_OF_AUDIT_TESTNET_EXECUTABLE_EVIDENCE_URI is unset"
        )

    manifest_json = os.environ.get(
        "PROOF_OF_AUDIT_TESTNET_EXECUTABLE_EVIDENCE_MANIFEST_JSON", ""
    ).strip()
    evidence_manifest = json.loads(manifest_json) if manifest_json else None

    created = testnet_context.create_audit(
        contract_address=testnet_context.smoke_fixture["address"],
        input_kind="deployed_address",
        submitted_by=f"testnet-exec-{uuid4().hex[:8]}",
    )
    published = testnet_context.publish_audit(created["id"])
    assert published["status"] == "published"

    challenged = testnet_context.challenge_audit(
        created["id"],
        proof_uri,
        challenger=f"exec-challenger-{uuid4().hex[:6]}",
        evidence_type="executable_test",
        execution_env="foundry",
        evidence_manifest=evidence_manifest,
        gas_action="executable_challenge",
    )
    assert challenged["status"] == "challenged"
    assert challenged["challenge"]["evidence_type"] == "executable_test"
    assert challenged["challenge"]["execution_env"] == "foundry"
    assert challenged["challenge"]["resolution_path"] == "manual_fallback"
    assert challenged["challenge"]["challenge_hash"]

    fetched = testnet_context.get_audit(created["id"])
    assert fetched["challenge"]["evidence_type"] == "executable_test"
    assert fetched["challenge"]["execution_env"] == "foundry"
    assert fetched["challenge"]["proof_uri"] == proof_uri
    assert fetched["challenge"]["challenge_hash"] == challenged["challenge"]["challenge_hash"]
    assert fetched["challenge"]["verification_status"]
    assert fetched["challenge"]["verification_summary"]
