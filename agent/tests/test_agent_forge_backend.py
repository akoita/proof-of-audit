import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import zipfile

import httpx
import pytest

from proof_of_audit_agent.agent_forge_backend import (
    AgentForgeBackend,
    AgentForgeExecutionError,
    AgentForgeRuntimeConfig,
)
from proof_of_audit_agent.auditor_backend import AuditSubmission


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


def _write_fake_agent_forge_script(
    path: Path,
    *,
    report_text: str | None = None,
    exit_code: int = 0,
    stderr_text: str = "",
    run_id: str = "run-123",
) -> Path:
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


def _runtime(
    tmp_path: Path,
    *,
    mode: str = "agent_forge",
    command: str,
    service_url: str | None = None,
) -> AgentForgeRuntimeConfig:
    return AgentForgeRuntimeConfig(
        mode=mode,
        command=command,
        runs_home=tmp_path / "home",
        service_base_url=service_url,
        service_poll_interval_seconds=0.0,
    )


def test_run_submission_parses_report_and_execution_metadata(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    source_file = repo_dir / "src" / "Vault.sol"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("contract Vault {}\n", encoding="utf-8")
    script = _write_fake_agent_forge_script(
        tmp_path / "fake-agent-forge",
        report_text=json.dumps(
            {
                "benchmark_id": "agent-forge-live",
                "summary": "Live audit completed.",
                "confidence": "medium",
                "findings": [
                    {
                        "finding_id": "finding-1",
                        "title": "Reentrancy in withdraw()",
                        "severity": "high",
                        "category": "reentrancy",
                        "description": "External call happens before state update.",
                        "impact": "Funds can be drained recursively.",
                        "recommendation": "Apply checks-effects-interactions.",
                        "confidence": "medium",
                        "affected_function": "withdraw(uint256)",
                        "source_path": str(source_file),
                        "start_line": 1,
                        "end_line": 1,
                        "evidence_uri": "ipfs://finding-1",
                        "detector": "agent_forge.live",
                    }
                ],
            },
            indent=2,
        ),
    )
    backend = AgentForgeBackend(
        _runtime(tmp_path, command=str(script)),
        tmp_path / "runtime",
    )

    result = backend.run_submission(
        AuditSubmission(
            audit_id="audit-123",
            input_kind="repository_url",
            repository_url=str(repo_dir),
            entry_contract="Vault",
        )
    )

    assert result is not None
    assert result.execution is not None
    assert result.execution.backend == "agent_forge"
    assert result.execution.status == "completed"
    assert result.execution.run_id == "run-123"
    assert result.execution.report_path is not None
    assert "Focus first on the contract named Vault." in (result.execution.task_prompt or "")
    assert result.report.benchmark_id == "agent-forge-live"
    assert result.report.finding_count == 1
    assert result.report.findings[0].source_path == "src/Vault.sol"
    assert result.report.findings[0].detector == "agent_forge.live"


def test_run_submission_strict_mode_requires_report_file(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    script = _write_fake_agent_forge_script(
        tmp_path / "fake-agent-forge",
        report_text=None,
    )
    backend = AgentForgeBackend(
        _runtime(tmp_path, command=str(script)),
        tmp_path / "runtime",
    )

    with pytest.raises(AgentForgeExecutionError, match="agent-report.json"):
        backend.run_submission(
            AuditSubmission(
                audit_id="audit-123",
                input_kind="repository_url",
                repository_url=str(repo_dir),
            )
        )


def test_run_submission_hybrid_mode_returns_none_when_report_is_missing(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    script = _write_fake_agent_forge_script(
        tmp_path / "fake-agent-forge",
        report_text=None,
    )
    backend = AgentForgeBackend(
        _runtime(tmp_path, mode="hybrid", command=str(script)),
        tmp_path / "runtime",
    )

    assert (
        backend.run_submission(
            AuditSubmission(
                audit_id="audit-123",
                input_kind="repository_url",
                repository_url=str(repo_dir),
            )
        )
        is None
    )


def test_run_submission_handles_malformed_json_and_nonzero_exit(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    malformed = _write_fake_agent_forge_script(
        tmp_path / "fake-malformed",
        report_text="{not-json",
    )
    strict_backend = AgentForgeBackend(
        _runtime(tmp_path, command=str(malformed)),
        tmp_path / "runtime-strict",
    )
    with pytest.raises(AgentForgeExecutionError):
        strict_backend.run_submission(
            AuditSubmission(
                audit_id="audit-malformed",
                input_kind="repository_url",
                repository_url=str(repo_dir),
            )
        )

    failing = _write_fake_agent_forge_script(
        tmp_path / "fake-failing",
        report_text=None,
        exit_code=2,
        stderr_text="boom",
    )
    hybrid_backend = AgentForgeBackend(
        _runtime(tmp_path, mode="hybrid", command=str(failing)),
        tmp_path / "runtime-hybrid",
    )
    assert (
        hybrid_backend.run_submission(
            AuditSubmission(
                audit_id="audit-failing",
                input_kind="repository_url",
                repository_url=str(repo_dir),
            )
        )
        is None
    )


def test_run_submission_supports_empty_and_partial_findings(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    empty_script = _write_fake_agent_forge_script(
        tmp_path / "fake-empty",
        report_text=json.dumps(
            {
                "summary": "No issues confirmed.",
                "confidence": "low",
                "findings": [],
            }
        ),
        run_id="run-empty",
    )
    empty_backend = AgentForgeBackend(
        _runtime(tmp_path, command=str(empty_script)),
        tmp_path / "runtime-empty",
    )
    empty_result = empty_backend.run_submission(
        AuditSubmission(
            audit_id="audit-empty",
            input_kind="repository_url",
            repository_url=str(repo_dir),
        )
    )
    assert empty_result is not None
    assert empty_result.report.findings == []

    partial_script = _write_fake_agent_forge_script(
        tmp_path / "fake-partial",
        report_text=json.dumps(
            {
                "summary": "Potential issue found.",
                "findings": [
                    {
                        "title": "Missing role check",
                        "severity": "medium",
                        "category": "access_control",
                    }
                ],
            }
        ),
        run_id="run-partial",
    )
    partial_backend = AgentForgeBackend(
        _runtime(tmp_path, command=str(partial_script)),
        tmp_path / "runtime-partial",
    )
    partial_result = partial_backend.run_submission(
        AuditSubmission(
            audit_id="audit-partial",
            input_kind="repository_url",
            repository_url=str(repo_dir),
        )
    )
    assert partial_result is not None
    finding = partial_result.report.findings[0]
    assert finding.affected_function is None
    assert finding.source_path is None
    assert finding.start_line is None
    assert finding.detector == "agent_forge.llm"
    assert finding.confidence == "medium"


def test_run_submission_uses_hosted_service_when_configured(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    source_file = repo_dir / "src" / "Vault.sol"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("contract Vault {}\n", encoding="utf-8")
    captured_requests: list[dict[str, object]] = []
    fake_client = FakeHostedHttpClient(
        responses=[
            {
                "status_code": 202,
                "json": {
                    "schema_version": "agent-forge-run-v1",
                    "run_id": "run_remote_123",
                    "status": "accepted",
                    "status_url": "/v1/runs/run_remote_123",
                    "report_url": "/v1/runs/run_remote_123/report",
                    "logs_url": "/v1/runs/run_remote_123/logs",
                    "created_at": "2026-03-25T10:30:00Z",
                },
            },
            {
                "status_code": 200,
                "json": {
                    "schema_version": "agent-forge-run-v1",
                    "run_id": "run_remote_123",
                    "status": "completed",
                    "status_url": "/v1/runs/run_remote_123",
                    "report_url": "/v1/runs/run_remote_123/report",
                    "logs_url": "/v1/runs/run_remote_123/logs",
                    "created_at": "2026-03-25T10:30:00Z",
                    "completed_at": "2026-03-25T10:30:05Z",
                },
            },
            {
                "status_code": 200,
                "json": {
                    "schema_version": "proof-of-audit-report-v1",
                    "run_id": "run_remote_123",
                    "summary": "Hosted service detected a reentrancy issue.",
                    "confidence": "medium",
                    "benchmark_id": "agent-forge-service-live",
                    "target": {
                        "submission_kind": "repository_url",
                        "entry_contract": "Vault",
                    },
                    "findings": [
                        {
                            "finding_id": "finding-1",
                            "title": "Reentrancy in withdraw()",
                            "severity": "high",
                            "category": "reentrancy",
                            "description": "External call happens before state update.",
                            "impact": "Funds can be drained recursively.",
                            "recommendation": "Apply checks-effects-interactions.",
                            "confidence": "medium",
                            "detector": "agent_forge.service.reentrancy",
                            "source_path": "src/Vault.sol",
                            "start_line": 1,
                            "end_line": 1,
                        }
                    ],
                    "stats": {
                        "finding_count": 1,
                        "max_severity": "high",
                        "severity_breakdown": {
                            "critical": 0,
                            "high": 1,
                            "medium": 0,
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
                    "run_id": "run_remote_123",
                    "artifacts": {
                        "run_dir": "/tmp/agent-forge/runs/run_remote_123",
                    },
                },
            },
        ],
        requests=captured_requests,
    )
    backend = AgentForgeBackend(
        _runtime(
            tmp_path,
            command="python -m agent_forge.cli",
            service_url="http://agent-forge.test",
        ),
        tmp_path / "runtime",
    )

    uploaded_archives: list[tuple[str, Path]] = []

    def fake_store_service_source_archive(
        _: AgentForgeBackend,
        audit_id: str,
        archive_path: Path,
    ) -> str:
        uploaded_archives.append((audit_id, archive_path))
        return "gs://proof-of-audit-source-bundles/audit-service-123.zip"

    with (
        patch(
            "proof_of_audit_agent.agent_forge_service_client.httpx.Client",
            return_value=fake_client,
        ),
        patch.object(
            AgentForgeBackend,
            "_store_service_source_archive",
            autospec=True,
            side_effect=fake_store_service_source_archive,
        ),
    ):
        result = backend.run_submission(
            AuditSubmission(
                audit_id="audit-service-123",
                input_kind="repository_url",
                network="base-sepolia",
                repository_url=str(repo_dir),
                entry_contract="Vault",
            )
        )

    assert result is not None
    assert result.execution is not None
    assert result.execution.backend == "agent_forge"
    assert result.execution.source == "agent_forge_service"
    assert result.execution.run_id == "run_remote_123"
    assert result.execution.status_url == "http://agent-forge.test/v1/runs/run_remote_123"
    assert result.execution.report_path == "http://agent-forge.test/v1/runs/run_remote_123/report"
    assert result.execution.logs_url == "http://agent-forge.test/v1/runs/run_remote_123/logs"
    assert result.execution.profile_id == "proof-of-audit-solidity-v1"
    assert result.execution.source_digest is not None
    assert result.report.benchmark_id == "agent-forge-service-live"
    assert result.report.findings[0].source_path == "src/Vault.sol"
    assert uploaded_archives
    upload_audit_id, upload_archive_path = uploaded_archives[0]
    assert upload_audit_id == "audit-service-123"
    assert upload_archive_path.exists()
    with zipfile.ZipFile(upload_archive_path) as archive:
        assert "src/Vault.sol" in archive.namelist()

    create_run_request = captured_requests[0]
    assert create_run_request["method"] == "POST"
    request_payload = create_run_request["json"]
    assert isinstance(request_payload, dict)
    assert request_payload["profile"]["id"] == "proof-of-audit-solidity-v1"
    assert request_payload["target"]["network"] == "base-sepolia"
    assert request_payload["source"]["uri"] == "gs://proof-of-audit-source-bundles/audit-service-123.zip"


def test_run_submission_rejects_hosted_service_with_local_source_storage(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "Vault.sol").write_text("contract Vault {}\n", encoding="utf-8")
    backend = AgentForgeBackend(
        _runtime(
            tmp_path,
            command="python -m agent_forge.cli",
            service_url="http://agent-forge.test",
        ),
        tmp_path / "runtime",
    )

    with pytest.raises(
        AgentForgeExecutionError,
        match="requires non-local source bundle storage",
    ):
        backend.run_submission(
            AuditSubmission(
                audit_id="audit-service-local-storage",
                input_kind="repository_url",
                repository_url=str(repo_dir),
                entry_contract="Vault",
            )
        )


def test_resolve_source_path_supports_file_uri_absolute_relative_and_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    archive_path = tmp_path / "bundle.zip"
    archive_path.write_bytes(b"zip")
    backend = AgentForgeBackend(
        _runtime(tmp_path, mode="hybrid", command="python -m agent_forge.cli"),
        tmp_path / "runtime",
    )

    assert (
        backend._resolve_source_path(
            input_kind="repository_url",
            repository_url=repo_dir.as_uri(),
            source_bundle_uri=None,
        )
        == repo_dir
    )
    assert (
        backend._resolve_source_path(
            input_kind="source_bundle",
            repository_url=None,
            source_bundle_uri=str(archive_path),
        )
        == archive_path
    )
    monkeypatch.chdir(tmp_path)
    assert (
        backend._resolve_source_path(
            input_kind="repository_url",
            repository_url="repo",
            source_bundle_uri=None,
        )
        == repo_dir
    )
    assert (
        backend._resolve_source_path(
            input_kind="repository_url",
            repository_url=str(tmp_path / "missing"),
            source_bundle_uri=None,
        )
        is None
    )


def test_run_submission_downloads_ipfs_source_bundle_before_live_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _write_fake_agent_forge_script(
        tmp_path / "fake-agent-forge",
        report_text=json.dumps(
            {
                "summary": "Live audit completed.",
                "confidence": "medium",
                "findings": [],
            }
        ),
    )
    backend = AgentForgeBackend(
        _runtime(tmp_path, command=str(script)),
        tmp_path / "runtime",
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
        assert req.full_url == "https://gateway.example/ipfs/QmBundle/UncheckedTreasury.sol"
        assert timeout == 15
        return FakeResponse(b"contract UncheckedTreasury {}\n")

    monkeypatch.setenv("PROOF_OF_AUDIT_IPFS_GATEWAY", "https://gateway.example/ipfs")
    monkeypatch.setattr(
        "proof_of_audit_agent.agent_forge_backend.request.urlopen",
        fake_urlopen,
    )

    result = backend.run_submission(
        AuditSubmission(
            audit_id="audit-123",
            input_kind="source_bundle",
            source_bundle_uri="ipfs://QmBundle/UncheckedTreasury.sol",
            entry_contract="UncheckedTreasury",
        )
    )

    assert result is not None
    assert result.execution is not None
    assert result.execution.workspace_dir is not None
    assert Path(result.execution.workspace_dir, "UncheckedTreasury.sol").exists()


def test_run_submission_materializes_verified_source_for_deployed_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _write_fake_agent_forge_script(
        tmp_path / "fake-agent-forge",
        report_text=json.dumps(
            {
                "summary": "Live audit completed.",
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
            }
        ),
    )
    backend = AgentForgeBackend(
        _runtime(tmp_path, command=str(script)),
        tmp_path / "runtime",
    )
    tempdir = tempfile.TemporaryDirectory(prefix="proof-of-audit-test-")
    source_root = Path(tempdir.name) / "source"
    (source_root / "src").mkdir(parents=True, exist_ok=True)
    (source_root / "src" / "Vault.sol").write_text("contract Vault {}\n", encoding="utf-8")

    monkeypatch.setattr(
        backend.deployed_address_source_resolver,
        "resolve",
        lambda **_: type(
            "ResolvedSource",
            (),
            {
                "path": source_root,
                "tempdir": tempdir,
                "entry_contract": "Vault",
                "source_uri": "sourcify://84532/0xabc0000000000000000000000000000000000000",
            },
        )(),
    )

    result = backend.run_submission(
        AuditSubmission(
            audit_id="audit-123",
            input_kind="deployed_address",
            chain_id=84532,
            contract_address="0xabc0000000000000000000000000000000000000",
        )
    )

    assert result is not None
    assert result.execution is not None
    assert result.execution.source_path == "sourcify://84532/0xabc0000000000000000000000000000000000000"
    assert result.report.contract_address == "0xabc0000000000000000000000000000000000000"
    assert result.report.findings[0].source_path == "src/Vault.sol"
    assert Path(result.execution.workspace_dir, "src", "Vault.sol").exists()


def test_prepare_workspace_copies_directory_unwraps_zip_and_preserves_sol_files(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source-repo"
    source_file = source_dir / "src" / "Vault.sol"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("contract Vault {}\n", encoding="utf-8")
    archive_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("wrapped/src/Vault.sol", "contract Vault {}\n")
    plain_sol_path = tmp_path / "SingleVault.sol"
    plain_sol_path.write_text("contract SingleVault {}\n", encoding="utf-8")
    backend = AgentForgeBackend(
        _runtime(tmp_path, mode="hybrid", command="python -m agent_forge.cli"),
        tmp_path / "runtime",
    )

    copied_workspace = backend._prepare_workspace("audit-dir", source_dir)
    copied_file = copied_workspace / "src" / "Vault.sol"
    assert copied_workspace == tmp_path / "runtime" / "agent-forge" / "audit-dir" / "repo"
    assert copied_file.exists()

    extracted_workspace = backend._prepare_workspace("audit-zip", archive_path)
    assert extracted_workspace.name == "wrapped"
    assert (extracted_workspace / "src" / "Vault.sol").exists()

    single_file_workspace = backend._prepare_workspace("audit-sol", plain_sol_path)
    assert single_file_workspace == tmp_path / "runtime" / "agent-forge" / "audit-sol" / "repo"
    assert (single_file_workspace / "SingleVault.sol").exists()


def test_prepare_workspace_replaces_existing_target_root(tmp_path: Path) -> None:
    source_dir = tmp_path / "source-repo"
    source_dir.mkdir()
    (source_dir / "Vault.sol").write_text("contract Vault {}\n", encoding="utf-8")
    backend = AgentForgeBackend(
        _runtime(tmp_path, mode="hybrid", command="python -m agent_forge.cli"),
        tmp_path / "runtime",
    )

    first_workspace = backend._prepare_workspace("audit-123", source_dir)
    stale_file = first_workspace.parent / "stale.txt"
    stale_file.write_text("stale\n", encoding="utf-8")

    second_workspace = backend._prepare_workspace("audit-123", source_dir)

    assert second_workspace.exists()
    assert not stale_file.exists()


def test_fallback_execution_respects_mode_gating(tmp_path: Path) -> None:
    deterministic_backend = AgentForgeBackend(
        _runtime(tmp_path, mode="deterministic", command="python -m agent_forge.cli"),
        tmp_path / "runtime-deterministic",
    )
    assert (
        deterministic_backend.fallback_execution(
            reason="no live path",
            live_attempted=False,
            source="safe-fallback",
        )
        is None
    )

    hybrid_backend = AgentForgeBackend(
        _runtime(tmp_path, mode="hybrid", command="python -m agent_forge.cli"),
        tmp_path / "runtime-hybrid",
    )
    fallback = hybrid_backend.fallback_execution(
        reason="no live path",
        live_attempted=True,
        source="safe-fallback",
    )
    assert fallback is not None
    assert fallback.backend == "deterministic"
    assert fallback.status == "fallback"
    assert fallback.fallback_used is True
    assert fallback.error == "no live path"


def test_deterministic_mode_short_circuits_and_strict_mode_rejects_unsupported_input(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    deterministic_backend = AgentForgeBackend(
        _runtime(tmp_path, mode="deterministic", command="python -m agent_forge.cli"),
        tmp_path / "runtime-deterministic",
    )
    assert (
        deterministic_backend.run_submission(
            AuditSubmission(
                audit_id="audit-123",
                input_kind="repository_url",
                repository_url=str(repo_dir),
            )
        )
        is None
    )

    strict_backend = AgentForgeBackend(
        _runtime(tmp_path, mode="agent_forge", command="python -m agent_forge.cli"),
        tmp_path / "runtime-strict",
    )
    with pytest.raises(AgentForgeExecutionError, match="does not support demo_fixture"):
        strict_backend.run_submission(
            AuditSubmission(
                audit_id="audit-124",
                input_kind="demo_fixture",
            )
        )
