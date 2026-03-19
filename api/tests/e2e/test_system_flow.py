from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any
import zipfile

import pytest

from api.tests.e2e.conftest import SystemStack


AUDIT_STATUS_RESOLVED = 3
CHALLENGE_RESOLUTION_UPHELD = 1
CHALLENGE_RESOLUTION_REJECTED = 2


def create_audit(
    stack: SystemStack,
    contract_address: str | None = None,
    *,
    submitted_by: str = "system-e2e",
    input_kind: str = "deployed_address",
    fixture_id: str | None = None,
    entry_contract: str | None = None,
    source_bundle_uri: str | None = None,
    source_bundle_label: str | None = None,
    repository_url: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input_kind": input_kind,
        "submitted_by": submitted_by,
    }
    if contract_address is not None:
        payload["contract_address"] = contract_address
    if fixture_id is not None:
        payload["fixture_id"] = fixture_id
    if entry_contract is not None:
        payload["entry_contract"] = entry_contract
    if source_bundle_uri is not None:
        payload["source_bundle_uri"] = source_bundle_uri
    if source_bundle_label is not None:
        payload["source_bundle_label"] = source_bundle_label
    if repository_url is not None:
        payload["repository_url"] = repository_url
    response = stack.client.post(
        "/audits",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def publish_audit(
    stack: SystemStack, audit_id: str, stake_wei: int | None = None
) -> dict[str, Any]:
    response = stack.client.post(
        f"/audits/{audit_id}/publish",
        json={
            "stake_wei": stake_wei or stack.config["required_stake_wei"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def challenge_audit(
    stack: SystemStack,
    audit_id: str,
    proof_uri: str,
    *,
    challenger: str = "whitehat-demo",
    evidence_type: str = "deterministic_fixture",
    execution_env: str | None = None,
    evidence_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "proof_uri": proof_uri,
        "challenger": challenger,
        "evidence_type": evidence_type,
    }
    if execution_env is not None:
        payload["execution_env"] = execution_env
    if evidence_manifest is not None:
        payload["evidence_manifest"] = evidence_manifest
    response = stack.client.post(
        f"/audits/{audit_id}/challenge",
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _write_fake_agent_forge_script(
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


def _write_source_bundle(path: Path, *, contract_name: str = "BundleVault") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"wrapped/src/{contract_name}.sol",
            f"pragma solidity ^0.8.20;\ncontract {contract_name} {{}}\n",
        )
    return path


@pytest.mark.system_e2e
def test_system_stack_exposes_live_contract_and_fixture_metadata(
    system_stack: SystemStack,
) -> None:
    health = system_stack.client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    auditor_service = system_stack.client.get("/auditor")
    assert auditor_service.status_code == 200
    assert auditor_service.json()["service_id"] == "proof-of-audit-auditor"
    assert auditor_service.json()["registration_kind"] == "offchain_manifest"
    assert auditor_service.json()["capability"] == "audit_contract"
    assert (
        auditor_service.json()["registration_uri"]
        == "https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json"
    )

    registration = system_stack.client.get("/auditor/registration")
    assert registration.status_code == 200
    registration_payload = registration.json()
    assert registration_payload["type"] == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    assert registration_payload["x-proof-of-audit"]["operator"] == "Proof-of-Audit"
    assert "audit_contract" in registration_payload["x-proof-of-audit"]["capabilities"]

    auditor_catalog = system_stack.client.get("/auditors")
    assert auditor_catalog.status_code == 200
    catalog_items = auditor_catalog.json()["items"]
    assert [item["service_id"] for item in catalog_items] == ["proof-of-audit-auditor"]

    plural_service = system_stack.client.get("/auditors/proof-of-audit-auditor")
    assert plural_service.status_code == 200
    assert plural_service.json()["service_id"] == "proof-of-audit-auditor"

    plural_registration = system_stack.client.get(
        "/auditors/proof-of-audit-auditor/registration"
    )
    assert plural_registration.status_code == 200
    assert plural_registration.json()["type"] == registration_payload["type"]

    assert system_stack.config["deployment_ready"] is True
    assert system_stack.config["network"] == "anvil-system-e2e"
    assert system_stack.config["chain_id"] == 31339
    assert system_stack.config["auditor"]["id"] == "proof-of-audit-auditor"
    assert (
        system_stack.config["auditor_service"]["manifest_schema"]
        == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    )

    fixture_ids = {fixture["id"] for fixture in system_stack.fixtures}
    assert fixture_ids == {
        "vulnerable-bank",
        "admin-setter",
        "clean-vault",
        "dual-risk-vault",
        "unchecked-treasury",
    }

    for fixture in system_stack.fixtures:
        code = system_stack.web3.eth.get_code(
            system_stack.web3.to_checksum_address(fixture["address"])
        )
        assert code and code != b"\x00"

    demo_fixture_audit = create_audit(
        system_stack,
        input_kind="demo_fixture",
        fixture_id="vulnerable-bank",
        submitted_by="fixture-dispatch",
    )
    assert demo_fixture_audit["submission"]["input_kind"] == "demo_fixture"
    assert demo_fixture_audit["submission"]["fixture_id"] == "vulnerable-bank"
    assert (
        demo_fixture_audit["contract_address"]
        == system_stack.fixture_by_id("vulnerable-bank")["address"]
    )
    assert demo_fixture_audit["report"]["benchmark_id"] == "reentrancy-bank"


@pytest.mark.system_e2e
def test_http_publish_and_verified_challenge_rejection_resolve_onchain(
    system_stack: SystemStack,
) -> None:
    fixture = system_stack.fixture_by_id("vulnerable-bank")
    created = create_audit(system_stack, fixture["address"])
    assert created["status"] == "draft"
    assert created["agent"]["id"] == "proof-of-audit-auditor"
    assert created["report"]["benchmark_id"] == "reentrancy-bank"
    assert created["report"]["finding_count"] == 1

    published = publish_audit(system_stack, created["id"])
    assert published["status"] == "published"
    assert published["onchain"]["agent_identity"] == "proof-of-audit-auditor"
    assert published["onchain"]["chain_id"] == 31339
    assert published["onchain"]["contract_address"] == system_stack.config["contract_address"]
    assert published["validation"] is None
    assert published["reputation_trail"] is None

    validation_request = system_stack.client.get(
        f"/audits/{created['id']}/validation/request"
    )
    assert validation_request.status_code == 404
    assert validation_request.json()["error"] == "validation_request_not_found"

    reputation_claim = system_stack.client.get(f"/audits/{created['id']}/reputation/claim")
    assert reputation_claim.status_code == 404
    assert reputation_claim.json()["error"] == "reputation_claim_not_found"

    challenged = challenge_audit(system_stack, created["id"], fixture["challenge_proof_uri"])
    assert challenged["status"] == "resolved"
    assert challenged["challenge"]["status"] == "rejected"
    assert challenged["challenge"]["resolution"] == "rejected"
    assert challenged["challenge"]["verification_status"] == "verified"
    assert challenged["challenge"]["resolution_path"] == "deterministic"
    assert challenged["challenge"]["resolve_tx_hash"].startswith("0x")

    validation_response = system_stack.client.get(
        f"/audits/{created['id']}/validation/response"
    )
    assert validation_response.status_code == 404
    assert validation_response.json()["error"] == "validation_response_not_found"

    reputation_resolution = system_stack.client.get(
        f"/audits/{created['id']}/reputation/resolution"
    )
    assert reputation_resolution.status_code == 404
    assert reputation_resolution.json()["error"] == "reputation_resolution_not_found"

    fetched = system_stack.client.get(f"/audits/{created['id']}")
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["status"] == "resolved"
    assert payload["challenge"]["status"] == "rejected"

    audit_record = system_stack.contract.functions.getAudit(payload["onchain"]["audit_id"]).call()
    assert int(audit_record[10]) == AUDIT_STATUS_RESOLVED
    assert int(audit_record[11]) == CHALLENGE_RESOLUTION_REJECTED


@pytest.mark.system_e2e
def test_invalid_evidence_requires_manual_resolution_over_http(
    system_stack: SystemStack,
) -> None:
    fixture = system_stack.fixture_by_id("clean-vault")
    created = create_audit(system_stack, fixture["address"], submitted_by="manual-review")
    publish_audit(system_stack, created["id"])

    challenged = challenge_audit(system_stack, created["id"], "ipfs://wrong-proof")
    assert challenged["status"] == "challenged"
    assert challenged["challenge"]["status"] == "opened"
    assert challenged["challenge"]["verification_status"] == "invalid_evidence"
    assert challenged["challenge"]["resolution_path"] == "manual_fallback"

    resolved = system_stack.client.post(
        f"/audits/{created['id']}/resolve",
        json={"upheld": True, "resolved_by": "arbiter-operator"},
    )
    assert resolved.status_code == 200, resolved.text
    payload = resolved.json()
    assert payload["status"] == "resolved"
    assert payload["challenge"]["status"] == "upheld"
    assert payload["challenge"]["resolution"] == "upheld"
    assert payload["challenge"]["resolve_tx_hash"].startswith("0x")

    audit_record = system_stack.contract.functions.getAudit(payload["onchain"]["audit_id"]).call()
    assert int(audit_record[10]) == AUDIT_STATUS_RESOLVED
    assert int(audit_record[11]) == CHALLENGE_RESOLUTION_UPHELD


@pytest.mark.system_e2e
def test_http_interface_rejects_duplicate_publish_and_duplicate_challenge(
    system_stack: SystemStack,
) -> None:
    fixture = system_stack.fixture_by_id("admin-setter")
    created = create_audit(system_stack, fixture["address"], submitted_by="duplicate-check")
    publish_audit(system_stack, created["id"])

    republish = system_stack.client.post(
        f"/audits/{created['id']}/publish",
        json={
            "stake_wei": system_stack.config["required_stake_wei"],
        },
    )
    assert republish.status_code == 400
    assert republish.json()["error"] == "invalid_payload"

    first_challenge = challenge_audit(system_stack, created["id"], "ipfs://wrong-proof")
    assert first_challenge["status"] == "challenged"

    second_challenge = system_stack.client.post(
        f"/audits/{created['id']}/challenge",
        json={
            "proof_uri": fixture["challenge_proof_uri"],
            "challenger": "second-whitehat",
        },
    )
    assert second_challenge.status_code == 400
    assert second_challenge.json()["error"] == "invalid_payload"


@pytest.mark.system_e2e
def test_http_interface_exposes_richer_multi_finding_reports(
    system_stack: SystemStack,
) -> None:
    fixture = system_stack.fixture_by_id("dual-risk-vault")
    created = create_audit(
        system_stack,
        fixture["address"],
        submitted_by="schema-check",
    )

    report = created["report"]
    assert report["benchmark_id"] == "dual-risk-vault"
    assert report["finding_count"] == 2
    assert report["severity_breakdown"]["high"] == 1
    assert report["severity_breakdown"]["medium"] == 1
    assert [finding["category"] for finding in report["findings"]] == [
        "access_control",
        "unchecked_external_call",
    ]
    assert [finding["evidence_uri"] for finding in report["findings"]] == [
        "ipfs://dual-risk-vault/owner-takeover",
        "ipfs://dual-risk-vault/emergency-payout-failure",
    ]


@pytest.mark.system_e2e
def test_http_interface_returns_structured_errors_for_unknown_and_invalid_requests(
    system_stack: SystemStack,
) -> None:
    missing = system_stack.client.get("/audits/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"] == "audit_not_found"

    invalid = system_stack.client.post("/audits", json={"submitted_by": "missing-address"})
    assert invalid.status_code == 422
    assert invalid.json()["error"] == "validation_error"


@pytest.mark.system_e2e
def test_agent_forge_mode_runs_live_backend_for_local_repository_and_source_bundle(
    system_stack_factory,
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "Vault.sol").write_text(
        "pragma solidity ^0.8.20;\ncontract Vault {}\n",
        encoding="utf-8",
    )
    source_bundle_path = _write_source_bundle(tmp_path / "bundle.zip")
    runs_home = tmp_path / "agent-forge-home"
    script = _write_fake_agent_forge_script(
        tmp_path / "fake-agent-forge",
        report_payload={
            "benchmark_id": "agent-forge-system-live",
            "summary": "Live agent-forge execution completed.",
            "confidence": "medium",
            "findings": [
                {
                    "finding_id": "agent-forge-system-live.finding-1",
                    "title": "Reentrancy in withdraw()",
                    "severity": "high",
                    "category": "reentrancy",
                    "description": "External call happens before state update.",
                    "impact": "Funds can be drained recursively.",
                    "recommendation": "Apply checks-effects-interactions.",
                    "confidence": "medium",
                    "affected_function": "withdraw(uint256)",
                    "source_path": "src/Vault.sol",
                    "start_line": 1,
                    "end_line": 1,
                    "detector": "agent_forge.live",
                }
            ],
        },
    )
    stack = system_stack_factory(
        env_overrides={
            "PROOF_OF_AUDIT_WORKER_RUNTIME_MODE": "agent_forge",
            "PROOF_OF_AUDIT_AGENT_FORGE_COMMAND": str(script),
            "PROOF_OF_AUDIT_AGENT_FORGE_RUNS_HOME": str(runs_home),
        }
    )

    repository_audit = create_audit(
        stack,
        input_kind="repository_url",
        repository_url=str(repo_dir),
        entry_contract="Vault",
        submitted_by="repo-live",
    )
    assert repository_audit["submission"]["input_kind"] == "repository_url"
    assert repository_audit["execution"]["backend"] == "agent_forge"
    assert repository_audit["execution"]["status"] == "completed"
    assert repository_audit["execution"]["run_id"] == "run-123"
    assert repository_audit["report"]["benchmark_id"] == "agent-forge-system-live"

    bundle_audit = create_audit(
        stack,
        input_kind="source_bundle",
        source_bundle_uri=str(source_bundle_path),
        entry_contract="BundleVault",
        submitted_by="bundle-live",
    )
    assert bundle_audit["submission"]["input_kind"] == "source_bundle"
    assert bundle_audit["execution"]["backend"] == "agent_forge"
    assert bundle_audit["execution"]["status"] == "completed"
    assert bundle_audit["report"]["benchmark_id"] == "agent-forge-system-live"


@pytest.mark.system_e2e
def test_hybrid_mode_falls_back_for_remote_repository_and_source_bundle(
    system_stack_factory,
) -> None:
    stack = system_stack_factory(
        env_overrides={
            "PROOF_OF_AUDIT_WORKER_RUNTIME_MODE": "hybrid",
        }
    )

    repository_audit = create_audit(
        stack,
        input_kind="repository_url",
        repository_url="https://github.com/example/not-local",
        entry_contract="Vault",
        submitted_by="repo-hybrid",
    )
    assert repository_audit["execution"]["backend"] == "deterministic"
    assert repository_audit["execution"]["status"] == "fallback"
    assert repository_audit["execution"]["source"] == "safe-fallback"
    assert repository_audit["report"]["benchmark_id"] == "repository-url"

    bundle_audit = create_audit(
        stack,
        input_kind="source_bundle",
        source_bundle_uri="https://example.com/bundles/reentrancy-bank.zip",
        entry_contract="VulnerableBank",
        submitted_by="bundle-hybrid",
    )
    assert bundle_audit["execution"]["backend"] == "deterministic"
    assert bundle_audit["execution"]["status"] == "fallback"
    assert bundle_audit["execution"]["source"] == "deterministic-benchmark"
    assert bundle_audit["report"]["benchmark_id"] == "reentrancy-bank"


@pytest.mark.system_e2e
def test_executable_evidence_requires_manual_review_when_it_matches_existing_findings(
    system_stack: SystemStack,
    forge_available: bool,
    tmp_path: Path,
) -> None:
    if not forge_available:
        pytest.skip("forge is required for executable-evidence system tests")

    fixture = system_stack.fixture_by_id("vulnerable-bank")
    created = create_audit(
        system_stack,
        fixture["address"],
        submitted_by="exec-match",
    )
    publish_audit(system_stack, created["id"])

    proof_path = tmp_path / "ChallengeEvidence.t.sol"
    proof_path.write_text(
        dedent(
            """
            pragma solidity ^0.8.20;

            interface IVulnerableBank {
                function withdraw(uint256 amount) external;
            }

            contract ChallengeEvidenceTest {
                function testReportedWithdrawPathStillExists() public pure {
                    require(true, "proof passes");
                }
            }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    challenged = challenge_audit(
        system_stack,
        created["id"],
        proof_path.as_uri(),
        evidence_type="executable_test",
        execution_env="foundry",
        challenger="whitehat-exec-match",
    )
    assert challenged["status"] == "challenged"
    challenge = challenged["challenge"]
    assert challenge["status"] == "opened"
    assert challenge["verification_status"] == "verified"
    assert challenge["advisory_verdict"] == "rejected"
    assert challenge["resolution_path"] == "manual_fallback"
    assert challenge["matched_findings"]
    assert challenge["execution_log"] is not None

    validation_response = system_stack.client.get(
        f"/audits/{created['id']}/validation/response"
    )
    assert validation_response.status_code == 404
    assert validation_response.json()["error"] == "validation_response_not_found"


@pytest.mark.system_e2e
def test_executable_evidence_can_advise_upheld_then_manual_resolution_updates_validation_trail(
    system_stack: SystemStack,
    forge_available: bool,
    tmp_path: Path,
) -> None:
    if not forge_available:
        pytest.skip("forge is required for executable-evidence system tests")

    fixture = system_stack.fixture_by_id("clean-vault")
    created = create_audit(
        system_stack,
        fixture["address"],
        submitted_by="exec-upheld",
    )
    publish_audit(system_stack, created["id"])

    proof_path = tmp_path / "CleanVaultChallenge.t.sol"
    proof_path.write_text(
        dedent(
            """
            pragma solidity ^0.8.20;

            contract CleanVaultChallengeTest {
                function privilegeEscalationScenario() internal pure returns (bool) {
                    return true;
                }

                function testUnreportedIssue() public pure {
                    require(privilegeEscalationScenario(), "proof passes");
                }
            }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    challenged = challenge_audit(
        system_stack,
        created["id"],
        proof_path.as_uri(),
        evidence_type="executable_test",
        execution_env="foundry",
        challenger="whitehat-exec-upheld",
    )
    assert challenged["status"] == "challenged"
    challenge = challenged["challenge"]
    assert challenge["status"] == "opened"
    assert challenge["verification_status"] == "verified"
    assert challenge["advisory_verdict"] == "upheld"
    assert challenge["resolution_path"] == "manual_fallback"
    assert any("privilege" in item for item in challenge["unmatched_findings"])

    resolved = system_stack.client.post(
        f"/audits/{created['id']}/resolve",
        json={"upheld": True, "resolved_by": "arbiter-operator"},
    )
    assert resolved.status_code == 200, resolved.text
    resolved_payload = resolved.json()
    assert resolved_payload["status"] == "resolved"
    assert resolved_payload["challenge"]["status"] == "upheld"
    assert resolved_payload["challenge"]["resolution"] == "upheld"

    validation_response = system_stack.client.get(
        f"/audits/{created['id']}/validation/response"
    )
    assert validation_response.status_code == 404
    assert validation_response.json()["error"] == "validation_response_not_found"

    reputation_resolution = system_stack.client.get(
        f"/audits/{created['id']}/reputation/resolution"
    )
    assert reputation_resolution.status_code == 404
    assert reputation_resolution.json()["error"] == "reputation_resolution_not_found"


@pytest.mark.system_e2e
def test_executable_evidence_marks_failed_foundry_runs_as_invalid_evidence(
    system_stack: SystemStack,
    forge_available: bool,
    tmp_path: Path,
) -> None:
    if not forge_available:
        pytest.skip("forge is required for executable-evidence system tests")

    fixture = system_stack.fixture_by_id("clean-vault")
    created = create_audit(
        system_stack,
        fixture["address"],
        submitted_by="exec-invalid",
    )
    publish_audit(system_stack, created["id"])

    proof_path = tmp_path / "FailingChallengeEvidence.t.sol"
    proof_path.write_text(
        dedent(
            """
            pragma solidity ^0.8.20;

            contract FailingChallengeEvidenceTest {
                function testFailurePath() public pure {
                    require(false, "expected failure");
                }
            }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    challenged = challenge_audit(
        system_stack,
        created["id"],
        proof_path.as_uri(),
        evidence_type="executable_test",
        execution_env="foundry",
        challenger="whitehat-exec-invalid",
    )
    assert challenged["status"] == "challenged"
    challenge = challenged["challenge"]
    assert challenge["status"] == "opened"
    assert challenge["verification_status"] == "invalid_evidence"
    assert challenge["advisory_verdict"] == "rejected"
    assert challenge["resolution_path"] == "manual_fallback"
