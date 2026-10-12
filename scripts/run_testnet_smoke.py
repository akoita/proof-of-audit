#!/usr/bin/env python3
from __future__ import annotations

import argparse
from html import escape as html_escape
import json
import os
from pathlib import Path
import re
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
SENSITIVE_ENV_VARS = (
    "PROOF_OF_AUDIT_TESTNET_API_URL",
    "PROOF_OF_AUDIT_TESTNET_RPC_URL",
    "PROOF_OF_AUDIT_TESTNET_PRIVATE_KEY",
    *OPTIONAL_ENV_VARS,
)
REQUIRED_TEST_SUFFIXES = (
    "test_preflight.test_base_sepolia_preflight_validates_configured_environment",
    "test_agent_forge_service_smoke.test_base_sepolia_deployed_address_uses_hosted_agent_forge_service",
    "test_agent_forge_service_smoke.test_base_sepolia_deployed_address_missing_verified_source_fails_without_fallback",
    "test_workflow_smoke.test_base_sepolia_plain_proof_uri_workflow_stays_open_until_manual_resolution",
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
    if name == "PROOF_OF_AUDIT_TESTNET_CHAIN_ID":
        if value:
            snapshot["value"] = value
    else:
        snapshot["redacted"] = True
    return snapshot


def _collect_manifest_secrets(value: Any, sensitive_context: bool = False) -> list[str]:
    if isinstance(value, dict):
        secrets: list[str] = []
        for key, nested in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            sensitive_field = sensitive_context or any(
                hint in normalized_key
                for hint in (
                    "key",
                    "token",
                    "secret",
                    "password",
                    "authorization",
                    "credential",
                    "private",
                    "url",
                    "uri",
                )
            )
            secrets.extend(_collect_manifest_secrets(nested, sensitive_field))
        return secrets
    if isinstance(value, list):
        return [
            secret
            for nested in value
            for secret in _collect_manifest_secrets(nested, sensitive_context)
        ]
    if isinstance(value, str) and value and (sensitive_context or "://" in value):
        return [value]
    return []


def _configured_secrets() -> list[str]:
    secrets: set[str] = set()
    for name in SENSITIVE_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            secrets.add(value)
            if name.endswith("MANIFEST_JSON"):
                try:
                    secrets.update(_collect_manifest_secrets(json.loads(value)))
                except (json.JSONDecodeError, TypeError):
                    pass

    for name, raw_value in os.environ.items():
        if name == "TESTNET_API_KEY" or name.endswith("_TESTNET_API_KEY"):
            value = raw_value.strip()
            if value:
                secrets.add(value)

    return sorted(secrets, key=len, reverse=True)


def _secret_variants(secret: str) -> set[str]:
    variants = {secret}
    json_escaped = json.dumps(secret, ensure_ascii=False)[1:-1]
    xml_escaped = html_escape(secret, quote=True)
    if json_escaped:
        variants.add(json_escaped)
    if xml_escaped:
        variants.add(xml_escaped)
    return variants


def _sanitize_text(value: str, secrets: list[str]) -> str:
    for secret in secrets:
        for variant in sorted(_secret_variants(secret), key=len, reverse=True):
            value = value.replace(variant, "[REDACTED]")
    return value


def _sanitize_value(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value, secrets)
    if isinstance(value, list):
        return [_sanitize_value(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item, secrets) for item in value)
    if isinstance(value, dict):
        return {
            _sanitize_text(key, secrets) if isinstance(key, str) else key:
            _sanitize_value(item, secrets)
            for key, item in value.items()
        }
    return value


def _sanitize_junit(junit_path: Path, secrets: list[str]) -> str | None:
    if not junit_path.exists():
        return None

    def fail_closed() -> str:
        try:
            junit_path.unlink(missing_ok=True)
        except OSError:
            try:
                junit_path.write_text("", encoding="utf-8")
            except OSError:
                pass
        return "JUnit XML could not be sanitized; its artifact was removed."

    def has_configured_secret(value: str) -> bool:
        return any(
            variant in value
            for secret in secrets
            for variant in _secret_variants(secret)
        )

    try:
        tree = ET.parse(junit_path)
    except ET.ParseError:
        # A malformed report cannot be structurally sanitized. Try exact text
        # replacement and keep it only if every configured value is gone.
        try:
            raw_xml = junit_path.read_text(encoding="utf-8", errors="replace")
            safe_xml = _sanitize_text(raw_xml, secrets)
            if has_configured_secret(safe_xml):
                return fail_closed()
            junit_path.write_text(safe_xml, encoding="utf-8")
            if has_configured_secret(junit_path.read_text(encoding="utf-8")):
                return fail_closed()
        except (OSError, UnicodeError):
            return fail_closed()
        return None
    except (OSError, UnicodeError):
        return fail_closed()

    root = tree.getroot()
    for node in root.iter():
        for name, value in list(node.attrib.items()):
            node.attrib[name] = _sanitize_text(value, secrets)
        if node.text:
            node.text = _sanitize_text(node.text, secrets)
        if node.tail:
            node.tail = _sanitize_text(node.tail, secrets)
    try:
        tree.write(junit_path, encoding="utf-8", xml_declaration=True)
        if has_configured_secret(junit_path.read_text(encoding="utf-8")):
            return fail_closed()
    except (OSError, UnicodeError, ET.ParseError):
        return fail_closed()
    return None


def _parse_junit(junit_path: Path) -> dict[str, Any]:
    if not junit_path.exists():
        return {"exists": False, "valid": False, "summary": {}, "tests": []}

    try:
        root = ET.fromstring(junit_path.read_text(encoding="utf-8"))
    except (ET.ParseError, OSError, UnicodeError) as exc:
        return {
            "exists": True,
            "valid": False,
            "error": f"JUnit XML could not be parsed: {exc}",
            "summary": {},
            "tests": [],
        }

    testcase_nodes = list(root.iter("testcase"))
    tests: list[dict[str, Any]] = []
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    try:
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
    except (TypeError, ValueError) as exc:
        return {
            "exists": True,
            "valid": False,
            "error": f"JUnit XML contains invalid testcase data: {exc}",
            "summary": {},
            "tests": [],
        }

    return {"exists": True, "valid": True, "summary": counts, "tests": tests}


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


def _write_report(
    report: dict[str, Any],
    json_path: Path,
    markdown_path: Path,
    secrets: list[str],
) -> int:
    report["finished_at"] = _now_iso()
    safe_report = _sanitize_value(report, secrets)
    _write_json(json_path, safe_report)
    markdown = _render_markdown(safe_report)
    markdown_path.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0 if safe_report["status"] == "passed" else 1


def _parse_structured_output(
    line: str,
    context_summary: dict[str, Any] | None,
    audit_artifacts: list[dict[str, Any]],
    failure_artifacts: list[dict[str, Any]],
    gas_summary: list[dict[str, Any]],
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    str | None,
]:
    marker, separator, payload = line.partition("=")
    if not separator:
        return context_summary, audit_artifacts, failure_artifacts, gas_summary, None

    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        return (
            context_summary,
            audit_artifacts,
            failure_artifacts,
            gas_summary,
            f"Malformed structured output for {marker}: {exc}",
        )

    if marker == "TESTNET_CONTEXT_SUMMARY":
        if not isinstance(parsed, dict):
            error = f"Structured output for {marker} must be a JSON object."
        else:
            context_summary = parsed
            error = None
    else:
        if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
            error = f"Structured output for {marker} must be a list of JSON objects."
        else:
            error = None
            if marker == "TESTNET_AUDIT_ARTIFACTS":
                audit_artifacts = parsed
            elif marker == "TESTNET_FAILURE_ARTIFACTS":
                failure_artifacts = parsed
            elif marker == "TESTNET_GAS_SUMMARY":
                gas_summary = parsed

    return context_summary, audit_artifacts, failure_artifacts, gas_summary, error


def _is_positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _is_valid_tx_hash(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{64}", value) is not None


def _validate_lifecycle_evidence(
    artifact: dict[str, Any], configured_chain_id: int | None
) -> list[str]:
    errors: list[str] = []
    evidence = artifact.get("lifecycle_evidence")
    if not isinstance(evidence, dict):
        return ["lifecycle_evidence must be a JSON object."]

    if configured_chain_id is None or type(evidence.get("chain_id")) is not int:
        errors.append("lifecycle_evidence.chain_id must match the configured integer chain ID.")
    elif evidence["chain_id"] != configured_chain_id:
        errors.append("lifecycle_evidence.chain_id does not match the configured chain ID.")

    evidence_contract = evidence.get("settlement_contract_address")
    artifact_contract = artifact.get("settlement_contract_address")
    if (
        not isinstance(evidence_contract, str)
        or not evidence_contract.strip()
        or not isinstance(artifact_contract, str)
        or not artifact_contract.strip()
        or evidence_contract.strip().lower() != artifact_contract.strip().lower()
    ):
        errors.append(
            "lifecycle_evidence.settlement_contract_address does not match the artifact settlement address."
        )

    evidence_audit_id = evidence.get("published_audit_id")
    artifact_audit_id = artifact.get("published_audit_id")
    if (
        not _is_positive_int(evidence_audit_id)
        or not _is_positive_int(artifact_audit_id)
        or evidence_audit_id != artifact_audit_id
    ):
        errors.append("lifecycle_evidence.published_audit_id does not match the artifact audit ID.")

    stake_wei = evidence.get("stake_wei")
    bond_wei = evidence.get("bond_wei")
    if not _is_positive_int(stake_wei):
        errors.append("lifecycle_evidence.stake_wei must be a positive integer.")
    if not _is_positive_int(bond_wei):
        errors.append("lifecycle_evidence.bond_wei must be a positive integer.")

    receipts = evidence.get("receipts")
    if not isinstance(receipts, dict):
        errors.append("lifecycle_evidence.receipts must be a JSON object.")
        receipts = {}

    receipt_hashes: dict[str, str] = {}
    block_numbers: dict[str, int] = {}
    for action in ("publish", "challenge", "resolve"):
        receipt = receipts.get(action)
        if not isinstance(receipt, dict):
            errors.append(f"lifecycle_evidence.receipts.{action} must be a JSON object.")
            continue

        tx_hash = receipt.get("tx_hash")
        if not _is_valid_tx_hash(tx_hash):
            errors.append(
                f"lifecycle_evidence.receipts.{action}.tx_hash must be a 32-byte hex transaction hash."
            )
        else:
            receipt_hashes[action] = tx_hash

        status = receipt.get("status")
        if type(status) is not int or status != 1:
            errors.append(f"lifecycle_evidence.receipts.{action}.status must equal 1.")

        block_number = receipt.get("block_number")
        if not _is_positive_int(block_number):
            errors.append(
                f"lifecycle_evidence.receipts.{action}.block_number must be a positive integer."
            )
        else:
            block_numbers[action] = block_number

        artifact_hash = artifact.get(f"{action}_tx_hash")
        if (
            tx_hash is None
            or not _is_valid_tx_hash(artifact_hash)
            or not _is_valid_tx_hash(tx_hash)
            or artifact_hash.lower() != tx_hash.lower()
        ):
            errors.append(
                f"artifact {action}_tx_hash does not match lifecycle_evidence.receipts.{action}.tx_hash."
            )

    if len(receipt_hashes) == 3 and len({value.lower() for value in receipt_hashes.values()}) != 3:
        errors.append("lifecycle_evidence receipt transaction hashes must be distinct.")

    ordered_actions = ("publish", "challenge", "resolve")
    if all(action in block_numbers for action in ordered_actions):
        if not (
            block_numbers["publish"]
            <= block_numbers["challenge"]
            <= block_numbers["resolve"]
        ):
            errors.append("lifecycle_evidence receipt block numbers must be nondecreasing.")

    payout = evidence.get("payout")
    if not isinstance(payout, dict):
        errors.append("lifecycle_evidence.payout must be a JSON object.")
    else:
        payout_tx_hash = payout.get("tx_hash")
        resolve_tx_hash = receipt_hashes.get("resolve")
        if (
            not _is_valid_tx_hash(payout_tx_hash)
            or resolve_tx_hash is None
            or payout_tx_hash.lower() != resolve_tx_hash.lower()
        ):
            errors.append("lifecycle_evidence.payout.tx_hash must match the resolve receipt.")

        beneficiary = payout.get("beneficiary")
        if (
            not isinstance(beneficiary, str)
            or re.fullmatch(r"0x[0-9a-fA-F]{40}", beneficiary) is None
            or int(beneficiary[2:], 16) == 0
        ):
            errors.append(
                "lifecycle_evidence.payout.beneficiary must be a nonzero 20-byte Ethereum address."
            )

        payout_amount = payout.get("amount_wei")
        if not _is_positive_int(payout_amount):
            errors.append("lifecycle_evidence.payout.amount_wei must be a positive integer.")
        elif _is_positive_int(stake_wei) and _is_positive_int(bond_wei):
            if payout_amount != stake_wei + bond_wei:
                errors.append(
                    "lifecycle_evidence.payout.amount_wei must equal stake_wei plus bond_wei."
                )

        if type(payout.get("resolution")) is not int or payout["resolution"] != 1:
            errors.append("lifecycle_evidence.payout.resolution must equal 1.")

    return errors


def _lifecycle_coverage_issue(
    audit_artifacts: list[dict[str, Any]], configured_chain_id: int | None
) -> str | None:
    candidates = [
        artifact
        for artifact in audit_artifacts
        if isinstance(artifact, dict) and "lifecycle_evidence" in artifact
    ]
    if not candidates:
        return "No captured audit artifact included lifecycle_evidence."

    failures: list[str] = []
    for index, artifact in enumerate(candidates, start=1):
        errors = _validate_lifecycle_evidence(artifact, configured_chain_id)
        if not errors:
            return None
        failures.append(f"Artifact with lifecycle evidence {index}: " + "; ".join(errors))
    return "No coherent lifecycle proof was captured:\n" + "\n".join(failures)


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
    secrets = _configured_secrets()

    # Remove only files this runner owns, so an early exit cannot leave proof
    # artifacts from a previous invocation available for upload.
    for artifact_path in (console_log_path, junit_path, json_path, markdown_path):
        artifact_path.unlink(missing_ok=True)

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
        report["issues"].append(
            "Live Base Sepolia smoke is not configured: missing "
            + ", ".join(missing_required)
            + "."
        )
        console_log_path.write_text(
            "Live Base Sepolia smoke was not started because required env is incomplete.\n",
            encoding="utf-8",
        )
        return _write_report(report, json_path, markdown_path, secrets)

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        "agent:api" if not existing_pythonpath else f"agent:api:{existing_pythonpath}"
    )

    context_summary: dict[str, Any] | None = None
    audit_artifacts: list[dict[str, Any]] = []
    failure_artifacts: list[dict[str, Any]] = []
    gas_summary: list[dict[str, Any]] = []
    structured_errors: list[str] = []
    process_error: str | None = None
    exit_code: int | None = None

    with console_log_path.open("w", encoding="utf-8") as log_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            process_error = f"Unable to start pytest: {exc}"
            safe_error = _sanitize_text(process_error, secrets)
            log_file.write(safe_error + "\n")
        else:
            try:
                if process.stdout is None:
                    raise RuntimeError("pytest output stream was not available")
                for line in process.stdout:
                    stripped = line.rstrip("\r\n")
                    if stripped.startswith(
                        (
                            "TESTNET_CONTEXT_SUMMARY=",
                            "TESTNET_AUDIT_ARTIFACTS=",
                            "TESTNET_FAILURE_ARTIFACTS=",
                            "TESTNET_GAS_SUMMARY=",
                        )
                    ):
                        (
                            context_summary,
                            audit_artifacts,
                            failure_artifacts,
                            gas_summary,
                            structured_error,
                        ) = _parse_structured_output(
                            stripped,
                            context_summary,
                            audit_artifacts,
                            failure_artifacts,
                            gas_summary,
                        )
                        if structured_error:
                            structured_errors.append(structured_error)

                    safe_line = _sanitize_text(line, secrets)
                    sys.stdout.write(safe_line)
                    log_file.write(safe_line)
                exit_code = process.wait()
            except Exception as exc:
                process_error = f"Unable to collect pytest output: {exc}"
                safe_error = _sanitize_text(process_error, secrets)
                log_file.write(safe_error + "\n")
                try:
                    exit_code = process.wait()
                except Exception:
                    exit_code = None

    junit_sanitization_error = _sanitize_junit(junit_path, secrets)

    junit_report = _parse_junit(junit_path)
    report["context"] = context_summary
    report["audit_artifacts"] = audit_artifacts
    report["failure_artifacts"] = failure_artifacts
    report["gas_summary"] = gas_summary
    report["pytest"] = {"exit_code": exit_code, "junit": junit_report}

    if process_error:
        report["status"] = "failed"
        report["issues"].append(process_error)
    elif exit_code != 0:
        report["status"] = "failed"
        report["issues"].append("Pytest returned a non-zero exit code.")
    else:
        report["status"] = "passed"

    if structured_errors:
        report["status"] = "failed"
        report["issues"].extend(structured_errors)
    if junit_sanitization_error:
        report["status"] = "failed"
        report["issues"].append(junit_sanitization_error)

    if args.require_live_env:
        coverage_issues: list[str] = []
        if not junit_report.get("exists"):
            coverage_issues.append("No JUnit report was produced.")
        elif not junit_report.get("valid"):
            coverage_issues.append(
                "JUnit report was malformed: "
                + junit_report.get("error", "unknown parse error")
            )
        elif not junit_report.get("tests"):
            coverage_issues.append("JUnit report was empty; no testcases were recorded.")

        for suffix in REQUIRED_TEST_SUFFIXES:
            test = _status_for_suffix(junit_report["tests"], suffix)
            if test is None:
                coverage_issues.append(f"{suffix} was missing from JUnit output")
                continue
            if test["status"] != "passed":
                detail = f": {test['detail']}" if test["detail"] else ""
                coverage_issues.append(
                    f"{test['id']} did not pass (status: {test['status']}){detail}"
                )
        if coverage_issues:
            report["status"] = "failed"
            report["issues"].append(
                "Required Base Sepolia smoke coverage was incomplete:\n"
                + "\n".join(coverage_issues)
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

    if args.require_live_env:
        raw_chain_id = os.environ.get("PROOF_OF_AUDIT_TESTNET_CHAIN_ID", "").strip()
        try:
            configured_chain_id = int(raw_chain_id)
        except ValueError:
            configured_chain_id = None
        lifecycle_issue = _lifecycle_coverage_issue(audit_artifacts, configured_chain_id)
        if lifecycle_issue:
            report["status"] = "failed"
            report["issues"].append(lifecycle_issue)

    return _write_report(report, json_path, markdown_path, secrets)


if __name__ == "__main__":
    raise SystemExit(main())
