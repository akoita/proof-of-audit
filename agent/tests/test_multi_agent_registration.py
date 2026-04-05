"""Tests for multi-agent identity registration (issue #280).

Validates the register-multi-agent-identities.py script logic by mocking
the ``cast`` subprocess calls and verifying the output structure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def agents_manifest(tmp_path: Path) -> Path:
    """Write a minimal agents manifest for testing."""
    manifest = {
        "schema_version": "agent-personas/v1",
        "agents": [
            {
                "service_id": "agent-reentrancy-hawk",
                "name": "Reentrancy Hawk",
                "profile": "reentrancy-specialist",
                "runtime_mode": "hybrid",
                "capabilities": ["audit_contract"],
                "detectors": ["reentrancy"],
                "challenge_strategy": "silent-monitor",
                "identity": {
                    "agent_id": 1,
                    "operator": "Proof-of-Audit",
                    "anvil_account_index": 1,
                },
            },
            {
                "service_id": "agent-access-sentinel",
                "name": "Access Control Sentinel",
                "profile": "access-control-specialist",
                "runtime_mode": "hybrid",
                "capabilities": ["audit_contract"],
                "detectors": ["access_control"],
                "challenge_strategy": "flag-for-review",
                "identity": {
                    "agent_id": 2,
                    "operator": "Proof-of-Audit",
                    "anvil_account_index": 2,
                },
            },
            {
                "service_id": "agent-full-spectrum",
                "name": "Full Spectrum Auditor",
                "profile": "full-spectrum-auditor",
                "runtime_mode": "hybrid",
                "capabilities": ["audit_contract", "review_challenge_evidence"],
                "detectors": ["reentrancy", "access_control", "unchecked_external_call"],
                "challenge_strategy": "auto-challenge",
                "identity": {
                    "agent_id": 3,
                    "operator": "Proof-of-Audit",
                    "anvil_account_index": 3,
                },
            },
        ],
    }
    path = tmp_path / "agents.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


@pytest.fixture()
def output_path(tmp_path: Path) -> Path:
    return tmp_path / "multi-agent-identities.json"


# ---------------------------------------------------------------------------
# Import the script module
# ---------------------------------------------------------------------------

def _import_register_module():
    """Import the registration script as a module."""
    import importlib.util
    # Navigate from agent/tests/ → project root → scripts/
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "register-multi-agent-identities.py"
    spec = importlib.util.spec_from_file_location("register_multi_agent", str(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnvilAccounts:
    def test_anvil_accounts_count(self):
        mod = _import_register_module()
        assert len(mod.ANVIL_ACCOUNTS) == 10

    def test_anvil_accounts_format(self):
        mod = _import_register_module()
        for addr, key in mod.ANVIL_ACCOUNTS:
            assert addr.startswith("0x")
            assert key.startswith("0x")
            assert len(key) == 66  # 0x + 64 hex chars


class TestResolveOperatorAccount:
    def test_valid_index(self):
        mod = _import_register_module()
        agent = {"service_id": "test", "identity": {"anvil_account_index": 3}}
        addr, key = mod._resolve_operator_account(agent)
        assert addr == mod.ANVIL_ACCOUNTS[3][0]
        assert key == mod.ANVIL_ACCOUNTS[3][1]

    def test_invalid_index(self):
        mod = _import_register_module()
        agent = {"service_id": "test", "identity": {"anvil_account_index": 99}}
        with pytest.raises(ValueError, match="anvil_account_index=99"):
            mod._resolve_operator_account(agent)

    def test_default_index(self):
        mod = _import_register_module()
        agent = {"service_id": "test", "identity": {}}
        addr, _ = mod._resolve_operator_account(agent)
        assert addr == mod.ANVIL_ACCOUNTS[0][0]


class TestRegistrationURI:
    def test_uri_format(self):
        mod = _import_register_module()
        uri = mod._agent_registration_uri("agent-reentrancy-hawk")
        assert "agent-reentrancy-hawk" in uri
        assert uri.startswith("https://")
        assert uri.endswith(".json")


class TestMainFunction:
    @patch("subprocess.run")
    def test_full_registration_flow(
        self, mock_run, agents_manifest, output_path
    ):
        """Test the main() function with mocked cast calls."""
        mod = _import_register_module()

        call_counter = {"next_id": 1}

        def mock_subprocess_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            cmd_str = " ".join(cmd)

            if "registerAgent" in cmd_str:
                # cast send registerAgent
                result.stdout = json.dumps({"transactionHash": f"0x{'ab' * 32}"})
            elif "nextAgentId" in cmd_str:
                # cast call nextAgentId
                call_counter["next_id"] += 1
                result.stdout = str(call_counter["next_id"])
            elif "balance" in cmd_str:
                # cast balance
                result.stdout = "1000000000000000000"  # 1 ETH
            elif "wallet address" in cmd_str:
                result.stdout = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
            else:
                result.stdout = ""
            return result

        mock_run.side_effect = mock_subprocess_run

        test_args = [
            "register-multi-agent-identities.py",
            "--registry-address", "0x" + "11" * 20,
            "--rpc-url", "http://127.0.0.1:8545",
            "--admin-private-key", "0x" + "aa" * 32,
            "--agents-manifest", str(agents_manifest),
            "--output", str(output_path),
            "--network", "anvil-local",
            "--chain-id", "31337",
        ]

        with patch.object(sys, "argv", test_args):
            result = mod.main()

        assert result == 0
        assert output_path.exists()

        output = json.loads(output_path.read_text(encoding="utf-8"))
        assert output["schema_version"] == "multi-agent-identities/v1"
        assert output["network"] == "anvil-local"
        assert output["chain_id"] == 31337
        assert output["agent_count"] == 3

        agents = output["agents"]
        assert "agent-reentrancy-hawk" in agents
        assert "agent-access-sentinel" in agents
        assert "agent-full-spectrum" in agents

        hawk = agents["agent-reentrancy-hawk"]
        assert hawk["profile"] == "reentrancy-specialist"
        assert hawk["detectors"] == ["reentrancy"]
        assert hawk["capabilities"] == ["audit_contract"]
        assert hawk["runtime_mode"] == "hybrid"
        assert hawk["register_tx_hash"].startswith("0x")

    def test_missing_manifest(self, output_path):
        mod = _import_register_module()
        test_args = [
            "register-multi-agent-identities.py",
            "--registry-address", "0x" + "11" * 20,
            "--rpc-url", "http://127.0.0.1:8545",
            "--admin-private-key", "0x" + "aa" * 32,
            "--agents-manifest", "/nonexistent/agents.json",
            "--output", str(output_path),
        ]
        with patch.object(sys, "argv", test_args):
            result = mod.main()
        assert result == 1


class TestOutputSchema:
    @patch("subprocess.run")
    def test_output_has_required_fields(
        self, mock_run, agents_manifest, output_path
    ):
        """Verify each agent record has all required fields per issue spec."""
        mod = _import_register_module()

        counter = {"n": 0}

        def mock_cast(cmd, **kwargs):
            r = MagicMock()
            r.returncode = 0
            cmd_str = " ".join(cmd)
            if "registerAgent" in cmd_str:
                r.stdout = json.dumps({"transactionHash": f"0x{'cc' * 32}"})
            elif "nextAgentId" in cmd_str:
                counter["n"] += 1
                r.stdout = str(counter["n"] + 1)
            elif "balance" in cmd_str:
                r.stdout = "9999999999999999999"
            else:
                r.stdout = ""
            return r

        mock_run.side_effect = mock_cast

        test_args = [
            "script",
            "--registry-address", "0x" + "22" * 20,
            "--rpc-url", "http://localhost:8545",
            "--admin-private-key", "0x" + "bb" * 32,
            "--agents-manifest", str(agents_manifest),
            "--output", str(output_path),
        ]
        with patch.object(sys, "argv", test_args):
            mod.main()

        output = json.loads(output_path.read_text(encoding="utf-8"))
        required_fields = {
            "service_id", "name", "agent_id", "operator_address",
            "operator_private_key", "registration_uri", "registry_address",
            "register_tx_hash", "profile", "runtime_mode", "detectors",
            "capabilities", "challenge_strategy",
        }

        for service_id, agent_record in output["agents"].items():
            missing = required_fields - set(agent_record.keys())
            assert not missing, f"Agent {service_id} missing: {missing}"
