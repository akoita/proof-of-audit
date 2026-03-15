from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_pre_commit_security_audit.py"


def run_plan(*files: str, report_path: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--files",
            *files,
            "--skip-commands",
            "--plan-json",
            "--report-path",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    start = result.stdout.find("{")
    assert start >= 0
    return json.loads(result.stdout[start:])


def test_contract_changes_trigger_contract_audit(tmp_path: Path) -> None:
    report_path = tmp_path / "contract-report.md"

    plan = run_plan(
        "contracts/src/ProofOfAudit.sol",
        report_path=report_path,
    )

    assert plan["relevant"] is True
    assert plan["contract_files"] == ["contracts/src/ProofOfAudit.sol"]
    assert plan["backend_files"] == []
    assert len(plan["commands"]) == 1
    assert plan["commands"][0]["label"] == "contract-security-regression"
    assert "forge" in plan["commands"][0]["command"]
    assert report_path.exists()


def test_backend_changes_trigger_backend_audit(tmp_path: Path) -> None:
    report_path = tmp_path / "backend-report.md"

    plan = run_plan(
        "api/proof_of_audit_api/service.py",
        "scripts/deploy-release.sh",
        report_path=report_path,
    )

    assert plan["relevant"] is True
    assert plan["contract_files"] == []
    assert plan["backend_files"] == [
        "api/proof_of_audit_api/service.py",
        "scripts/deploy-release.sh",
    ]
    assert len(plan["commands"]) == 1
    assert plan["commands"][0]["label"] == "backend-security-regression"
    assert "pytest" in plan["commands"][0]["command"]
    assert "OpenZeppelin Skills" in report_path.read_text(encoding="utf-8")


def test_unrelated_changes_do_not_trigger_extra_audits(tmp_path: Path) -> None:
    report_path = tmp_path / "no-op-report.md"

    plan = run_plan(
        "web/app/page.tsx",
        "docs/DEMO_SCRIPT.md",
        report_path=report_path,
    )

    assert plan["relevant"] is False
    assert plan["commands"] == []
    assert report_path.exists()
