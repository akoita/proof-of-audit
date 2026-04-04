"""Tests for capability-scoped detector execution (issue #275).

Verifies that the ``detectors`` parameter on ``analyze_repository``,
``AgentForgeRuntimeConfig``, and the CLI correctly scopes which static
analysis detector families execute.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from proof_of_audit_agent.live_auditor import ALL_DETECTORS, analyze_repository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VULNERABLE_CONTRACT = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract VulnerableBank {
    address public owner;
    mapping(address => uint256) public balances;

    function deposit() public payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() public {
        uint256 amount = balances[msg.sender];
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success);
        balances[msg.sender] = 0;
    }

    function setOwner(address newOwner) public {
        owner = newOwner;
    }

    function execute(address target) public {
        target.call("");
    }
}
"""


@pytest.fixture()
def contract_dir(tmp_path: Path) -> Path:
    sol = tmp_path / "VulnerableBank.sol"
    sol.write_text(_VULNERABLE_CONTRACT, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Unit tests — analyze_repository with detectors
# ---------------------------------------------------------------------------


class TestAnalyzeRepositoryScoping:
    def test_all_detectors_by_default(self, contract_dir: Path) -> None:
        result = analyze_repository(contract_dir)
        categories = {f["category"] for f in result["findings"]}
        assert "reentrancy" in categories
        assert "access_control" in categories
        assert result["supported_checks"] == sorted(ALL_DETECTORS)

    def test_reentrancy_only(self, contract_dir: Path) -> None:
        result = analyze_repository(contract_dir, detectors=frozenset({"reentrancy"}))
        categories = {f["category"] for f in result["findings"]}
        assert "reentrancy" in categories
        assert "access_control" not in categories
        assert "unchecked_external_call" not in categories
        assert result["supported_checks"] == ["reentrancy"]

    def test_access_control_only(self, contract_dir: Path) -> None:
        result = analyze_repository(contract_dir, detectors=frozenset({"access_control"}))
        categories = {f["category"] for f in result["findings"]}
        assert "access_control" in categories
        assert "reentrancy" not in categories
        assert result["supported_checks"] == ["access_control"]

    def test_multiple_subset(self, contract_dir: Path) -> None:
        chosen = frozenset({"reentrancy", "access_control"})
        result = analyze_repository(contract_dir, detectors=chosen)
        categories = {f["category"] for f in result["findings"]}
        assert "reentrancy" in categories
        assert "access_control" in categories
        assert "unchecked_external_call" not in categories
        assert result["supported_checks"] == ["access_control", "reentrancy"]

    def test_wildcard_runs_all(self, contract_dir: Path) -> None:
        result = analyze_repository(contract_dir, detectors=frozenset({"*"}))
        categories = {f["category"] for f in result["findings"]}
        assert "reentrancy" in categories
        assert result["supported_checks"] == sorted(ALL_DETECTORS)

    def test_none_runs_all(self, contract_dir: Path) -> None:
        result = analyze_repository(contract_dir, detectors=None)
        assert result["supported_checks"] == sorted(ALL_DETECTORS)

    def test_unknown_detector_raises(self, contract_dir: Path) -> None:
        with pytest.raises(ValueError, match="Unknown detector families"):
            analyze_repository(contract_dir, detectors=frozenset({"does_not_exist"}))

    def test_summary_includes_scope_label(self, contract_dir: Path) -> None:
        result = analyze_repository(contract_dir, detectors=frozenset({"reentrancy"}))
        assert "detectors: reentrancy" in result["summary"]

    def test_summary_all_label(self, contract_dir: Path) -> None:
        result = analyze_repository(contract_dir)
        assert "detectors: all" in result["summary"]


# ---------------------------------------------------------------------------
# Integration test — CLI --detectors flag
# ---------------------------------------------------------------------------


class TestCLIDetectorsFlag:
    def test_cli_detectors_flag(self, contract_dir: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "proof_of_audit_agent.agent_forge_cli",
                "run",
                "--task", "test audit",
                "--repo", str(contract_dir),
                "--detectors", "reentrancy",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        report_path = contract_dir / ".proof-of-audit" / "agent-report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        categories = {f["category"] for f in report["findings"]}
        assert "reentrancy" in categories
        assert "access_control" not in categories
        assert report["supported_checks"] == ["reentrancy"]

    def test_cli_no_detectors_flag_runs_all(self, contract_dir: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "proof_of_audit_agent.agent_forge_cli",
                "run",
                "--task", "test audit",
                "--repo", str(contract_dir),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        report_path = contract_dir / ".proof-of-audit" / "agent-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["supported_checks"] == sorted(ALL_DETECTORS)


# ---------------------------------------------------------------------------
# Config / Runtime integration
# ---------------------------------------------------------------------------


class TestRuntimeConfigScoping:
    def test_runtime_config_detectors_default(self) -> None:
        from proof_of_audit_agent.agent_forge_backend import AgentForgeRuntimeConfig

        config = AgentForgeRuntimeConfig()
        assert config.detectors is None
        assert config.audit_profile is None

    def test_runtime_config_detectors_set(self) -> None:
        from proof_of_audit_agent.agent_forge_backend import AgentForgeRuntimeConfig

        config = AgentForgeRuntimeConfig(
            detectors=("reentrancy",),
            audit_profile="reentrancy-hawk",
        )
        assert config.detectors == ("reentrancy",)
        assert config.audit_profile == "reentrancy-hawk"

    def test_worker_runtime_threads_detectors(self) -> None:
        from proof_of_audit_agent.runtime import WorkerRuntimeConfig

        cfg = WorkerRuntimeConfig.from_values(
            detectors=("reentrancy", "access_control"),
            audit_profile="access-sentinel",
        )
        assert cfg.agent_forge.detectors == ("reentrancy", "access_control")
        assert cfg.agent_forge.audit_profile == "access-sentinel"


# ---------------------------------------------------------------------------
# Task prompt scoping
# ---------------------------------------------------------------------------


class TestTaskPromptScoping:
    def test_prompt_includes_scoped_families(self) -> None:
        from proof_of_audit_agent.agent_forge_backend import (
            AgentForgeBackend,
            AgentForgeRuntimeConfig,
        )

        config = AgentForgeRuntimeConfig(
            detectors=("reentrancy", "access_control"),
            audit_profile="test-profile",
        )
        backend = AgentForgeBackend(config, Path("/tmp"))
        prompt = backend._build_task_prompt(entry_contract="Test.sol")
        assert "reentrancy" in prompt
        assert "access control" in prompt
        assert "unchecked" not in prompt.lower()
        assert "test-profile" in prompt

    def test_prompt_default_scope(self) -> None:
        from proof_of_audit_agent.agent_forge_backend import (
            AgentForgeBackend,
            AgentForgeRuntimeConfig,
        )

        config = AgentForgeRuntimeConfig()
        backend = AgentForgeBackend(config, Path("/tmp"))
        prompt = backend._build_task_prompt(entry_contract=None)
        assert "reentrancy" in prompt
        assert "access control" in prompt
        assert "unchecked external calls" in prompt
