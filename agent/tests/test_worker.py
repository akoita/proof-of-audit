import json
from pathlib import Path

import pytest
from proof_of_audit_agent.worker import AuditWorker
from proof_of_audit_agent.runtime import WorkerRuntimeConfig


def test_known_contract_returns_deterministic_finding() -> None:
    worker = AuditWorker()

    report = worker.run_audit("0x1000000000000000000000000000000000000001")

    assert report.benchmark_id == "reentrancy-bank"
    assert len(report.findings) == 1
    assert report.max_severity == 3
    assert report.findings[0].evidence_uri == "ipfs://reentrancy-bank/withdraw-drain"


def test_multi_finding_benchmark_returns_richer_schema() -> None:
    worker = AuditWorker()

    report = worker.run_audit("0x1000000000000000000000000000000000000004")

    assert report.benchmark_id == "dual-risk-vault"
    assert report.finding_count == 2
    assert report.max_severity == 3
    assert report.severity_breakdown["high"] == 1
    assert report.severity_breakdown["medium"] == 1
    assert report.findings[0].finding_id == "dual-risk-vault.rotate-owner.missing-access-control"
    assert report.findings[1].affected_function == "emergencyPayout(uint256)"


def test_unknown_contract_is_safe_fallback() -> None:
    worker = AuditWorker()

    report = worker.run_audit("0x1234000000000000000000000000000000000000")

    assert report.benchmark_id == "unknown"
    assert report.confidence == "low"
    assert report.findings == []
    assert report.finding_count == 0


def test_manifest_fixture_address_maps_to_benchmark(tmp_path) -> None:
    manifest = tmp_path / "demo-fixtures.localhost.json"
    manifest.write_text(
        json.dumps(
            {
                "fixtures": [
                    {
                        "id": "unchecked-treasury",
                        "label": "Unchecked Treasury",
                        "contract_name": "UncheckedTreasury",
                        "entry_contract": "UncheckedTreasury",
                        "benchmark_id": "unchecked-treasury",
                        "address": "0x9999000000000000000000000000000000000004",
                        "challenge_proof_uri": "ipfs://unchecked-treasury/unchecked-call-failure",
                        "note": "Imported registry and unchecked external call",
                        "source_path": "demo/contracts/UncheckedTreasury.sol",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    worker = AuditWorker(manifest)
    report = worker.run_audit("0x9999000000000000000000000000000000000004")

    assert report.benchmark_id == "unchecked-treasury"
    assert report.max_severity == 2
    assert len(report.findings) == 1


def test_repository_submission_uses_agent_forge_backend(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "Vault.sol").write_text("contract Vault {}", encoding="utf-8")

    runs_home = tmp_path / "home"
    script = tmp_path / "fake-agent-forge"
    script.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
repo = Path(args[args.index("--repo") + 1])
report_path = repo / ".proof-of-audit" / "agent-report.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps({
    "benchmark_id": "agent-forge-live",
    "summary": "Agent Forge found a reentrancy path in the live repository review.",
    "confidence": "medium",
    "findings": [{
        "title": "Reentrancy in withdraw()",
        "severity": "high",
        "category": "reentrancy",
        "description": "The external call happens before state is updated.",
        "impact": "Funds can be drained recursively.",
        "recommendation": "Apply checks-effects-interactions.",
        "confidence": "medium",
        "affected_function": "withdraw(uint256)",
        "source_path": "Vault.sol",
        "start_line": 1,
        "end_line": 1,
        "detector": "agent_forge.live"
    }]
}, indent=2))
run_dir = Path(os.environ["HOME"]) / ".agent-forge" / "runs" / "run-123"
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "run.json").write_text(json.dumps({
    "id": "run-123",
    "repo_path": str(repo),
    "state": "completed"
}))
""",
        encoding="utf-8",
    )
    script.chmod(0o755)

    worker = AuditWorker(
        runtime=WorkerRuntimeConfig.from_values(
            mode="agent_forge",
            agent_forge_command=str(script),
            agent_forge_runs_home=runs_home,
        ),
        workspace_root=tmp_path / "runtime",
    )

    result = worker.run_submission(
        audit_id="audit-123",
        input_kind="repository_url",
        repository_url=str(repo_dir),
        entry_contract="Vault",
    )

    assert result.execution is not None
    assert result.execution.backend == "agent_forge"
    assert result.execution.status == "completed"
    assert result.execution.run_id == "run-123"
    assert result.report.benchmark_id == "agent-forge-live"
    assert result.report.finding_count == 1
    assert result.report.findings[0].detector == "agent_forge.live"


def test_repository_submission_falls_back_in_hybrid_mode() -> None:
    worker = AuditWorker(
        runtime=WorkerRuntimeConfig.from_values(mode="hybrid"),
    )

    result = worker.run_submission(
        audit_id="audit-456",
        input_kind="repository_url",
        repository_url="https://github.com/example/not-local",
        entry_contract="Vault",
    )

    assert result.execution is not None
    assert result.execution.fallback_used is True
    assert result.report.benchmark_id == "repository-url"


def test_source_bundle_submission_falls_back_to_deterministic_benchmark() -> None:
    worker = AuditWorker(
        runtime=WorkerRuntimeConfig.from_values(mode="hybrid"),
    )

    result = worker.run_submission(
        audit_id="audit-source-1",
        input_kind="source_bundle",
        source_bundle_uri="https://example.com/bundles/reentrancy-bank.zip",
        entry_contract="VulnerableBank",
    )

    assert result.execution is not None
    assert result.execution.fallback_used is True
    assert result.execution.source == "deterministic-benchmark"
    assert result.report.benchmark_id == "reentrancy-bank"


def test_source_bundle_submission_uses_safe_fallback_when_no_benchmark_matches() -> None:
    worker = AuditWorker(
        runtime=WorkerRuntimeConfig.from_values(mode="hybrid"),
    )

    result = worker.run_submission(
        audit_id="audit-source-2",
        input_kind="source_bundle",
        source_bundle_uri="https://example.com/bundles/unknown.zip",
        entry_contract="CustomVault",
    )

    assert result.execution is not None
    assert result.execution.fallback_used is True
    assert result.execution.source == "safe-fallback"
    assert result.report.benchmark_id == "source-bundle"


def test_repository_submission_requires_local_path_in_strict_live_mode() -> None:
    worker = AuditWorker(
        runtime=WorkerRuntimeConfig.from_values(mode="agent_forge"),
    )

    with pytest.raises(Exception):
        worker.run_submission(
            audit_id="audit-789",
            input_kind="repository_url",
            repository_url="https://github.com/example/not-local",
        )
