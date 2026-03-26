#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any
import xml.etree.ElementTree as ET

from datetime import datetime, timezone


ROOT_DIR = Path(__file__).resolve().parents[1]
REQUIRED_ENV_VARS = (
    "PROOF_OF_AUDIT_TESTNET_API_URL",
    "PROOF_OF_AUDIT_TESTNET_RPC_URL",
    "PROOF_OF_AUDIT_TESTNET_PRIVATE_KEY",
    "PROOF_OF_AUDIT_TESTNET_CHAIN_ID",
)
OPTIONAL_ENV_VARS = (
    "PROOF_OF_AUDIT_TESTNET_EXECUTABLE_EVIDENCE_URI",
    "PROOF_OF_AUDIT_TESTNET_EXECUTABLE_EVIDENCE_MANIFEST_JSON",
)
REQUIRED_TEST_SUFFIXES = (
    "test_preflight.test_base_sepolia_preflight_validates_configured_environment",
    "test_agent_forge_service_smoke.test_base_sepolia_deployed_address_uses_hosted_agent_forge_service",
    "test_agent_forge_service_smoke.test_base_sepolia_deployed_address_missing_verified_source_fails_without_fallback",
    "test_workflow_smoke.test_base_sepolia_plain_proof_uri_workflow_stays_open_onchain",
    "test_workflow_smoke.test_base_sepolia_manual_resolution_workflow_resolves_onchain",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_git_ref(*args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _github_run_url() -> str | None:
    server = os.environ.get("GITHUB_SERVER_URL", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if server and repository and run_id:
        return f"{server}/{repository}/actions/runs/{run_id}"
    return None


def _env_snapshot(name: str) -> dict[str, Any]:
    raw_value = os.environ.get(name)
    value = raw_value.strip() if raw_value is not None else ""
    snapshot: dict[str, Any] = {"configured": bool(value)}
    if name.endswith("PRIVATE_KEY"):
        snapshot["redacted"] = True
    elif value:
        snapshot["value"] = value
    return snapshot


def _parse_junit(junit_path: Path) -> dict[str, Any]:
    if not junit_path.exists():
        return {"exists": False, "summary": {}, "tests": []}

    root = ET.fromstring(junit_path.read_text())
    testcase_nodes = list(root.iter("testcase"))
    tests: list[dict[str, Any]] = []
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    for node in testcase_nodes:
        classname = node.attrib.get("classname", "")
        name = node.attrib.get("name", "")
        duration = float(node.attrib.get("time", "0") or "0")
        test_id = f"{classname}.{name}" if classname else name

        status = "passed"
        detail = ""
        if (failure := node.find("failure")) is not None:
            status = "failed"
            detail = (failure.attrib.get("message") or failure.text or "").strip()
        elif (error := node.find("error")) is not None:
            status = "error"
            detail = (error.attrib.get("message") or error.text or "").strip()
        elif (skipped := node.find("skipped")) is not None:
            status = "skipped"
            detail = (skipped.attrib.get("message") or skipped.text or "").strip()

        counts_key = "errors" if status == "error" else status
        counts[counts_key] += 1
        tests.append(
            {
                "id": test_id,
                "classname": classname,
                "name": name,
                "status": status,
                "detail": detail,
                "duration_seconds": duration,
            }
        )

    return {"exists": True, "summary": counts, "tests": tests}


def _status_for_suffix(tests: list[dict[str, Any]], suffix: str) -> dict[str, Any] | None:
    for test in tests:
        if test["id"].endswith(suffix):
            return test
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Base Sepolia Smoke Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Started at (UTC): `{report['started_at']}`",
        f"- Finished at (UTC): `{report['finished_at']}`",
        f"- Command: `{report['command']}`",
    ]

    git_info = report.get("git", {})
    if git_info.get("head_sha"):
        lines.append(f"- Git SHA: `{git_info['head_sha']}`")
    if git_info.get("head_branch"):
        lines.append(f"- Git branch: `{git_info['head_branch']}`")

    github_actions = report.get("github_actions", {})
    if github_actions.get("run_url"):
        lines.append(f"- GitHub Actions run: {github_actions['run_url']}")

    lines.extend(["", "## Environment", ""])
    for name in REQUIRED_ENV_VARS:
        snapshot = report["environment"]["required"][name]
        suffix = "configured" if snapshot["configured"] else "missing"
        if "value" in snapshot:
            lines.append(f"- `{name}`: {suffix} (`{snapshot['value']}`)")
        else:
            lines.append(f"- `{name}`: {suffix}")
    for name in OPTIONAL_ENV_VARS:
        snapshot = report["environment"]["optional"][name]
        suffix = "configured" if snapshot["configured"] else "unset"
        if "value" in snapshot:
            lines.append(f"- `{name}`: {suffix} (`{snapshot['value']}`)")
        else:
            lines.append(f"- `{name}`: {suffix}")

    pytest_report = report.get("pytest", {})
    lines.extend(["", "## Pytest", ""])
    if pytest_report.get("junit", {}).get("exists"):
        summary = pytest_report["junit"]["summary"]
        lines.append(
            "- Summary: "
            f"{summary.get('passed', 0)} passed, "
            f"{summary.get('failed', 0)} failed, "
            f"{summary.get('errors', 0)} errors, "
            f"{summary.get('skipped', 0)} skipped"
        )
        for suffix in REQUIRED_TEST_SUFFIXES:
            test = _status_for_suffix(pytest_report["junit"]["tests"], suffix)
            label = suffix.split(".")[-1]
            if test is None:
                lines.append(f"- `{label}`: missing from JUnit output")
            elif test["detail"]:
                lines.append(f"- `{label}`: `{test['status']}` ({test['detail']})")
            else:
                lines.append(f"- `{label}`: `{test['status']}`")
    else:
        lines.append("- No JUnit report was produced.")
    lines.append(f"- Exit code: `{pytest_report.get('exit_code')}`")
    lines.append(f"- Console log: `{report['artifacts']['console_log']}`")

    context = report.get("context")
    if context:
        lines.extend(["", "## Runtime Context", "", "```json", json.dumps(context, indent=2), "```"])

    audit_artifacts = report.get("audit_artifacts", [])
    lines.extend(["", "## Audit Artifacts", ""])
    if audit_artifacts:
        lines.extend(["```json", json.dumps(audit_artifacts, indent=2), "```"])
    else:
        lines.append("- No publish/challenge/resolve artifacts were captured.")

    failure_artifacts = report.get("failure_artifacts", [])
    lines.extend(["", "## Failure Artifacts", ""])
    if failure_artifacts:
        lines.extend(["```json", json.dumps(failure_artifacts, indent=2), "```"])
    else:
        lines.append("- No failed submission artifacts were captured.")

    gas_summary = report.get("gas_summary", [])
    if gas_summary:
        lines.extend(["", "## Gas Summary", "", "```json", json.dumps(gas_summary, indent=2), "```"])

    issues = report.get("issues", [])
    lines.extend(["", "## Issues", ""])
    if issues:
        for issue in issues:
            lines.append(f"- {issue}")
    else:
        lines.append("- None.")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-dir", default=".tmp/testnet-smoke")
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--require-live-env", action="store_true")
    args = parser.parse_args()

    artifacts_dir = (ROOT_DIR / args.artifacts_dir).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    console_log_path = artifacts_dir / "pytest-output.log"
    junit_path = artifacts_dir / "junit.xml"
    json_path = artifacts_dir / "smoke-report.json"
    markdown_path = artifacts_dir / "smoke-report.md"

    command = [
        args.python_bin,
        "-m",
        "pytest",
        "-m",
        "testnet_smoke",
        "api/tests/testnet",
        "-rA",
        f"--junitxml={junit_path}",
    ]
    command_str = shlex.join(command)
    started_at = _now_iso()

    report: dict[str, Any] = {
        "status": "pending",
        "started_at": started_at,
        "finished_at": started_at,
        "command": command_str,
        "git": {
            "head_sha": _read_git_ref("rev-parse", "HEAD"),
            "head_branch": _read_git_ref("branch", "--show-current"),
        },
        "github_actions": {
            "run_url": _github_run_url(),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "environment": {
            "required": {name: _env_snapshot(name) for name in REQUIRED_ENV_VARS},
            "optional": {name: _env_snapshot(name) for name in OPTIONAL_ENV_VARS},
        },
        "context": None,
        "audit_artifacts": [],
        "failure_artifacts": [],
        "gas_summary": [],
        "issues": [],
        "pytest": {"exit_code": None, "junit": {"exists": False, "summary": {}, "tests": []}},
        "artifacts": {
            "console_log": str(console_log_path.relative_to(ROOT_DIR)),
            "junit_xml": str(junit_path.relative_to(ROOT_DIR)),
            "json_report": str(json_path.relative_to(ROOT_DIR)),
            "markdown_report": str(markdown_path.relative_to(ROOT_DIR)),
        },
    }

    missing_required = [
        name
        for name, snapshot in report["environment"]["required"].items()
        if not snapshot["configured"]
    ]
    if args.require_live_env and missing_required:
        report["status"] = "blocked"
        report["finished_at"] = _now_iso()
        report["issues"].append(
            "Live Base Sepolia smoke is not configured: missing "
            + ", ".join(missing_required)
            + "."
        )
        console_log_path.write_text(
            "Live Base Sepolia smoke was not started because required env is incomplete.\n"
        )
        _write_json(json_path, report)
        markdown_path.write_text(_render_markdown(report))
        print(markdown_path.read_text(), end="")
        return 1

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        "agent:api" if not existing_pythonpath else f"agent:api:{existing_pythonpath}"
    )

    context_summary: dict[str, Any] | None = None
    audit_artifacts: list[dict[str, Any]] = []
    failure_artifacts: list[dict[str, Any]] = []
    gas_summary: list[dict[str, Any]] = []

    with console_log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=ROOT_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log_file.write(line)
            stripped = line.rstrip("\n")
            if stripped.startswith("TESTNET_CONTEXT_SUMMARY="):
                context_summary = json.loads(stripped.split("=", 1)[1])
            elif stripped.startswith("TESTNET_AUDIT_ARTIFACTS="):
                audit_artifacts = json.loads(stripped.split("=", 1)[1])
            elif stripped.startswith("TESTNET_FAILURE_ARTIFACTS="):
                failure_artifacts = json.loads(stripped.split("=", 1)[1])
            elif stripped.startswith("TESTNET_GAS_SUMMARY="):
                gas_summary = json.loads(stripped.split("=", 1)[1])
        exit_code = process.wait()

    junit_report = _parse_junit(junit_path)
    report["finished_at"] = _now_iso()
    report["context"] = context_summary
    report["audit_artifacts"] = audit_artifacts
    report["failure_artifacts"] = failure_artifacts
    report["gas_summary"] = gas_summary
    report["pytest"] = {"exit_code": exit_code, "junit": junit_report}

    if exit_code != 0:
        report["status"] = "failed"
        report["issues"].append("Pytest returned a non-zero exit code.")
    else:
        report["status"] = "passed"

    if args.require_live_env and junit_report.get("exists"):
        required_skips: list[str] = []
        for suffix in REQUIRED_TEST_SUFFIXES:
            test = _status_for_suffix(junit_report["tests"], suffix)
            if test is None:
                required_skips.append(f"{suffix} was missing from JUnit output")
                continue
            if test["status"] == "skipped":
                required_skips.append(
                    f"{test['id']} was skipped: {test['detail'] or 'no reason reported'}"
                )
        if required_skips:
            report["status"] = "failed"
            report["issues"].append(
                "Required Base Sepolia smoke coverage did not execute:\n"
                + "\n".join(required_skips)
            )

    if args.require_live_env and report["status"] == "passed" and not audit_artifacts:
        report["status"] = "failed"
        report["issues"].append("No structured publish/challenge artifacts were captured.")

    if args.require_live_env and report["status"] == "passed":
        hosted_artifacts = [
            artifact
            for artifact in audit_artifacts
            if artifact.get("execution_source") == "agent_forge_service"
        ]
        if not hosted_artifacts:
            report["status"] = "failed"
            report["issues"].append(
                "No captured audit artifact proved that the hosted agent-forge service path was used."
            )

    _write_json(json_path, report)
    markdown_path.write_text(_render_markdown(report))
    print(markdown_path.read_text(), end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
