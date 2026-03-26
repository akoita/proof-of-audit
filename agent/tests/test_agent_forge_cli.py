import json
import os
from pathlib import Path
import subprocess
import sys

from proof_of_audit_agent.live_auditor import analyze_repository


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "agent"


def test_cli_runs_live_analysis_and_writes_report(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "VulnerableBank.sol").write_text(
        "\n".join(
            [
                "pragma solidity ^0.8.28;",
                "contract VulnerableBank {",
                "    mapping(address => uint256) public balances;",
                "    function withdraw(uint256 amount) external {",
                "        (bool ok, ) = msg.sender.call{value: amount}(\"\");",
                "        require(ok, \"send failed\");",
                "        balances[msg.sender] -= amount;",
                "    }",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    home_dir = tmp_path / "home"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "proof_of_audit_agent.agent_forge_cli",
            "run",
            "--task",
            "Audit the repository",
            "--repo",
            str(repo_dir),
        ],
        env={
            **os.environ,
            "HOME": str(home_dir),
            "PYTHONPATH": str(PACKAGE_ROOT),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(
        (repo_dir / ".proof-of-audit" / "agent-report.json").read_text(encoding="utf-8")
    )
    assert report["benchmark_id"] == "agent-forge-live"
    assert report["findings"]
    assert report["findings"][0]["category"] == "reentrancy"
    run_dirs = list((home_dir / ".agent-forge" / "runs").iterdir())
    assert len(run_dirs) == 1
    run_payload = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_payload["state"] == "completed"
    assert run_payload["repo_path"] == str(repo_dir.resolve())


def test_cli_reports_clean_result_when_no_supported_issue_is_found(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CleanVault.sol").write_text(
        "\n".join(
            [
                "pragma solidity ^0.8.28;",
                "contract CleanVault {",
                "    address public immutable owner;",
                "    constructor() { owner = msg.sender; }",
                "    modifier onlyOwner() { require(msg.sender == owner, \"not owner\"); _; }",
                "    function sweep(address payable to, uint256 amount) external onlyOwner {",
                "        (bool ok, ) = to.call{value: amount}(\"\");",
                "        require(ok, \"send failed\");",
                "    }",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "proof_of_audit_agent.agent_forge_cli",
            "run",
            "--task",
            "Audit the repository",
            "--repo",
            str(repo_dir),
        ],
        env={**os.environ, "PYTHONPATH": str(PACKAGE_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(
        (repo_dir / ".proof-of-audit" / "agent-report.json").read_text(encoding="utf-8")
    )
    assert report["findings"] == []
    assert "did not confirm" in report["summary"].lower()


def test_analyze_repository_does_not_skip_absolute_lib_path_components(tmp_path: Path) -> None:
    repo_dir = tmp_path / "lib" / "repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "VulnerableBank.sol").write_text(
        "\n".join(
            [
                "pragma solidity ^0.8.28;",
                "contract VulnerableBank {",
                "    mapping(address => uint256) public balances;",
                "    function withdraw(uint256 amount) external {",
                "        (bool ok, ) = msg.sender.call{value: amount}(\"\");",
                "        require(ok, \"send failed\");",
                "        balances[msg.sender] -= amount;",
                "    }",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    report = analyze_repository(repo_dir)

    assert len(report["findings"]) == 1
    assert report["findings"][0]["category"] == "reentrancy"
