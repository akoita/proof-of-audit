from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

from scripts import run_testnet_smoke as runner


@pytest.fixture
def configured_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(runner, "_read_git_ref", lambda *_args: None)
    monkeypatch.setattr(sys, "argv", ["run_testnet_smoke.py", "--require-live-env"])
    for name, value in {
        "PROOF_OF_AUDIT_TESTNET_API_URL": "https://test-api.example.invalid",
        "PROOF_OF_AUDIT_TESTNET_RPC_URL": "https://test-rpc.example.invalid",
        "PROOF_OF_AUDIT_TESTNET_PRIVATE_KEY": "0xprivate-test-key-0123456789",
        "PROOF_OF_AUDIT_TESTNET_CHAIN_ID": "84532",
    }.items():
        monkeypatch.setenv(name, value)
    for name in runner.OPTIONAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("PROOF_OF_AUDIT_TESTNET_API_KEY", raising=False)
    return tmp_path / ".tmp" / "testnet-smoke"


def _junit_xml(
    *,
    statuses: dict[str, str] | None = None,
    omitted: set[str] | None = None,
    output: str = "",
) -> str:
    statuses = statuses or {}
    omitted = omitted or set()
    suite = ET.Element("testsuite")
    for suffix in runner.REQUIRED_TEST_SUFFIXES:
        if suffix in omitted:
            continue
        classname, name = suffix.rsplit(".", 1)
        testcase = ET.SubElement(
            suite,
            "testcase",
            {"classname": classname, "name": name, "time": "0.01"},
        )
        if suffix in statuses:
            status = statuses[suffix]
            child = ET.SubElement(testcase, status)
            child.set("message", f"controlled {status} result")
        if output:
            system_out = ET.SubElement(testcase, "system-out")
            system_out.text = output
    return ET.tostring(suite, encoding="unicode")


def _fake_popen(
    monkeypatch: pytest.MonkeyPatch,
    *,
    junit_xml: str | None,
    stdout: str = "",
    returncode: int = 0,
) -> list[list[str]]:
    commands: list[list[str]] = []

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = io.StringIO(stdout)

        def wait(self) -> int:
            return returncode

    def fake_popen(command: list[str], **_kwargs: object) -> FakeProcess:
        commands.append(command)
        junit_arg = next(item for item in command if item.startswith("--junitxml="))
        junit_path = Path(junit_arg.split("=", 1)[1])
        if junit_xml is not None:
            junit_path.write_text(junit_xml, encoding="utf-8")
        return FakeProcess()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    return commands


def _hosted_artifact(**extra: object) -> dict[str, object]:
    return {"execution_source": "agent_forge_service", **extra}


def _lifecycle_artifact() -> dict[str, object]:
    publish_hash = "0x" + "1" * 64
    challenge_hash = "0x" + "2" * 64
    resolve_hash = "0x" + "3" * 64
    settlement_address = "0x" + "a" * 40
    audit_id = 12345
    return {
        "audit_id": "manual-fixture-audit",
        "published_audit_id": audit_id,
        "settlement_contract_address": settlement_address,
        "publish_tx_hash": publish_hash,
        "challenge_tx_hash": challenge_hash,
        "resolve_tx_hash": resolve_hash,
        "lifecycle_evidence": {
            "chain_id": 84532,
            "settlement_contract_address": settlement_address,
            "published_audit_id": audit_id,
            "receipts": {
                "publish": {"tx_hash": publish_hash, "block_number": 100, "status": 1},
                "challenge": {"tx_hash": challenge_hash, "block_number": 101, "status": 1},
                "resolve": {"tx_hash": resolve_hash, "block_number": 101, "status": 1},
            },
            "stake_wei": 3,
            "bond_wei": 2,
            "payout": {
                "tx_hash": resolve_hash,
                "beneficiary": "0x" + "c" * 40,
                "amount_wei": 5,
                "resolution": 1,
            },
        },
    }


def _read_report(artifacts_dir: Path) -> dict[str, object]:
    return json.loads((artifacts_dir / "smoke-report.json").read_text(encoding="utf-8"))


def test_missing_live_environment_clears_old_outputs_without_starting_pytest(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in runner.REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    configured_runner.mkdir(parents=True)
    for filename in (
        "pytest-output.log",
        "junit.xml",
        "smoke-report.json",
        "smoke-report.md",
    ):
        (configured_runner / filename).write_text("stale proof", encoding="utf-8")

    def unexpected_start(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pytest must not start without the live environment")

    monkeypatch.setattr(runner.subprocess, "Popen", unexpected_start)

    assert runner.main() == 1

    report = _read_report(configured_runner)
    assert report["status"] == "blocked"
    assert not (configured_runner / "junit.xml").exists()
    for path in configured_runner.iterdir():
        assert "stale proof" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("junit_xml", "expected_issue"),
    [
        (None, "No JUnit report was produced"),
        ("<testsuite>", "JUnit report was malformed"),
        ("<testsuite />", "JUnit report was empty"),
    ],
    ids=["absent", "malformed", "empty"],
)
def test_strict_mode_rejects_absent_malformed_and_empty_junit(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
    junit_xml: str | None,
    expected_issue: str,
) -> None:
    configured_runner.mkdir(parents=True)
    (configured_runner / "junit.xml").write_text(
        _junit_xml(), encoding="utf-8"
    )
    output = "TESTNET_AUDIT_ARTIFACTS=[{}]\n".format(
        json.dumps(_hosted_artifact())
    )
    _fake_popen(monkeypatch, junit_xml=junit_xml, stdout=output)

    assert runner.main() == 1

    report = _read_report(configured_runner)
    assert report["status"] == "failed"
    assert any(expected_issue in issue for issue in report["issues"])
    if junit_xml is None:
        assert not (configured_runner / "junit.xml").exists()


@pytest.mark.parametrize(
    ("statuses", "omitted", "expected_issue"),
    [
        ({runner.REQUIRED_TEST_SUFFIXES[0]: "skipped"}, set(), "status: skipped"),
        ({runner.REQUIRED_TEST_SUFFIXES[0]: "failure"}, set(), "status: failed"),
        ({runner.REQUIRED_TEST_SUFFIXES[0]: "error"}, set(), "status: error"),
        ({}, {runner.REQUIRED_TEST_SUFFIXES[0]}, "was missing from JUnit output"),
    ],
    ids=["skipped", "failed", "errored", "missing"],
)
def test_strict_mode_rejects_each_nonpassing_required_case(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
    statuses: dict[str, str],
    omitted: set[str],
    expected_issue: str,
) -> None:
    output = "TESTNET_AUDIT_ARTIFACTS=[{}]\n".format(
        json.dumps(_hosted_artifact())
    )
    _fake_popen(
        monkeypatch,
        junit_xml=_junit_xml(statuses=statuses, omitted=omitted),
        stdout=output,
    )

    assert runner.main() == 1

    report = _read_report(configured_runner)
    assert report["status"] == "failed"
    assert any(expected_issue in issue for issue in report["issues"])


def test_required_coverage_and_hosted_artifact_pass_and_redact_sensitive_values(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api_url = "https://sensitive-api.example.invalid/tenant-secret"
    rpc_url = "https://sensitive-rpc.example.invalid/chain-secret"
    private_key = "0xsensitive-private-key-0123456789"
    evidence_uri = "evidence://sensitive-evidence-secret"
    manifest_url = "https://manifest.example.invalid/proof-secret"
    manifest_token = "manifest-token-secret-123456"
    evidence_manifest = json.dumps(
        {
            "evidence_url": manifest_url,
            "credentials": {"token": manifest_token},
            "execution_env": "foundry",
        },
        separators=(",", ":"),
    )
    testnet_api_key = "sensitive-testnet-api-key-987654"
    monkeypatch.setenv("PROOF_OF_AUDIT_TESTNET_API_URL", api_url)
    monkeypatch.setenv("PROOF_OF_AUDIT_TESTNET_RPC_URL", rpc_url)
    monkeypatch.setenv("PROOF_OF_AUDIT_TESTNET_PRIVATE_KEY", private_key)
    monkeypatch.setenv("PROOF_OF_AUDIT_TESTNET_EXECUTABLE_EVIDENCE_URI", evidence_uri)
    monkeypatch.setenv(
        "PROOF_OF_AUDIT_TESTNET_EXECUTABLE_EVIDENCE_MANIFEST_JSON", evidence_manifest
    )
    monkeypatch.setenv("TESTNET_API_KEY", testnet_api_key)
    evidence_data = json.loads(evidence_manifest)
    context = {
        "api_url": api_url,
        "rpc_url": rpc_url,
        "private_key": private_key,
        "evidence_uri": evidence_uri,
        "manifest": evidence_data,
        "api_key": testnet_api_key,
    }
    artifact = _hosted_artifact(
        note=api_url,
        evidence_uri=evidence_uri,
        manifest=evidence_data,
        token=testnet_api_key,
    )
    stdout = "\n".join(
        [
            f"configured manifest: {evidence_manifest}",
            "TESTNET_CONTEXT_SUMMARY=" + json.dumps(context),
        "TESTNET_AUDIT_ARTIFACTS="
        + json.dumps([artifact, _hosted_artifact(), _lifecycle_artifact()]),
            f"ordinary output: {api_url} {rpc_url} {private_key} {evidence_uri} {testnet_api_key}",
        ]
    ) + "\n"
    junit = _junit_xml(output=" ".join([api_url, rpc_url, private_key, evidence_uri, testnet_api_key]))
    _fake_popen(monkeypatch, junit_xml=junit, stdout=stdout)

    assert runner.main() == 0

    captured = capsys.readouterr().out
    report = _read_report(configured_runner)
    assert report["status"] == "passed"
    assert report["environment"]["required"]["PROOF_OF_AUDIT_TESTNET_CHAIN_ID"]["value"] == "84532"
    all_outputs = [captured]
    all_outputs.extend(path.read_text(encoding="utf-8") for path in configured_runner.iterdir())
    for secret in (
        api_url,
        rpc_url,
        private_key,
        evidence_uri,
        evidence_manifest,
        manifest_url,
        manifest_token,
        testnet_api_key,
    ):
        assert all(secret not in content for content in all_outputs)
    assert report["context"]["manifest"]["execution_env"] == "foundry"


def test_coherent_lifecycle_evidence_can_be_separate_from_hosted_artifact(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = [_hosted_artifact(), _lifecycle_artifact()]
    output = "TESTNET_AUDIT_ARTIFACTS=" + json.dumps(artifacts) + "\n"
    _fake_popen(monkeypatch, junit_xml=_junit_xml(), stdout=output)

    assert runner.main() == 0
    assert _read_report(configured_runner)["status"] == "passed"


def test_unsanitizable_junit_is_removed_and_fails_strict_report(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = "TESTNET_AUDIT_ARTIFACTS=" + json.dumps(
        [_hosted_artifact(), _lifecycle_artifact()]
    ) + "\n"
    _fake_popen(
        monkeypatch,
        junit_xml=_junit_xml(output="https://test-api.example.invalid"),
        stdout=output,
    )

    def fail_xml_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("controlled JUnit write failure")

    monkeypatch.setattr(runner.ET.ElementTree, "write", fail_xml_write)

    assert runner.main() == 1

    report = _read_report(configured_runner)
    assert report["status"] == "failed"
    assert any("could not be sanitized" in issue for issue in report["issues"])
    assert not (configured_runner / "junit.xml").exists()


@pytest.mark.parametrize(
    ("mutation", "expected_issue"),
    [
        ("absentcycle", "No captured audit artifact included lifecycle_evidence"),
        ("missingpayout", "lifecycle_evidence.payout must be a JSON object"),
        ("wrongamount", "amount_wei must equal stake_wei plus bond_wei"),
        ("malformedbeneficiary", "beneficiary must be a nonzero 20-byte Ethereum address"),
        ("failedreceipt", "receipts.challenge.status must equal 1"),
        ("mismatchhash", "artifact challenge_tx_hash does not match"),
        ("mismatchcontract", "does not match the artifact settlement address"),
        ("mismatchid", "published_audit_id does not match the artifact audit ID"),
        ("mismatchchain", "does not match the configured chain ID"),
        ("booleanchain", "chain_id must match the configured integer chain ID"),
        ("booleanstake", "stake_wei must be a positive integer"),
        ("booleanbond", "bond_wei must be a positive integer"),
        ("booleanstatus", "receipts.publish.status must equal 1"),
        ("booleanblock", "receipts.resolve.block_number must be a positive integer"),
        ("booleanamount", "payout.amount_wei must be a positive integer"),
        ("booleanresolution", "payout.resolution must equal 1"),
        ("blockorder", "receipt block numbers must be nondecreasing"),
        ("duplicatehash", "receipt transaction hashes must be distinct"),
        ("invalidhash", "publish.tx_hash must be a 32-byte hex transaction hash"),
        ("mismatchpayout", "payout.tx_hash must match the resolve receipt"),
    ],
    ids=[
        "absent-cycle",
        "missing-payout",
        "wrong-amount",
        "malformed-beneficiary",
        "failed-receipt",
        "mismatched-hash",
        "mismatched-contract",
        "mismatched-audit-id",
        "mismatched-chain",
        "boolean-chain-id",
        "boolean-stake",
        "boolean-bond",
        "boolean-receipt-status",
        "boolean-block-number",
        "boolean-payout-amount",
        "boolean-resolution",
        "out-of-order-blocks",
        "duplicate-receipt-hash",
        "invalid-receipt-hash",
        "mismatched-payout-hash",
    ],
)
def test_strict_mode_rejects_incoherent_lifecycle_evidence(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_issue: str,
) -> None:
    artifacts = [_hosted_artifact()]
    if mutation != "absentcycle":
        artifact = _lifecycle_artifact()
        evidence = artifact["lifecycle_evidence"]
        assert isinstance(evidence, dict)
        receipts = evidence["receipts"]
        assert isinstance(receipts, dict)
        payout = evidence["payout"]
        assert isinstance(payout, dict)

        if mutation == "missingpayout":
            evidence.pop("payout")
        elif mutation == "wrongamount":
            payout["amount_wei"] = 4
        elif mutation == "malformedbeneficiary":
            payout["beneficiary"] = "0x1234"
        elif mutation == "failedreceipt":
            receipts["challenge"]["status"] = 0
        elif mutation == "mismatchhash":
            artifact["challenge_tx_hash"] = "0x" + "4" * 64
        elif mutation == "mismatchcontract":
            evidence["settlement_contract_address"] = "0x" + "d" * 40
        elif mutation == "mismatchid":
            evidence["published_audit_id"] = 12346
        elif mutation == "mismatchchain":
            evidence["chain_id"] = 84533
        elif mutation == "booleanchain":
            evidence["chain_id"] = True
        elif mutation == "booleanstake":
            evidence["stake_wei"] = True
        elif mutation == "booleanbond":
            evidence["bond_wei"] = True
        elif mutation == "booleanstatus":
            receipts["publish"]["status"] = True
        elif mutation == "booleanblock":
            receipts["resolve"]["block_number"] = True
        elif mutation == "booleanamount":
            payout["amount_wei"] = True
        elif mutation == "booleanresolution":
            payout["resolution"] = True
        elif mutation == "blockorder":
            receipts["publish"]["block_number"] = 102
        elif mutation == "duplicatehash":
            duplicate_hash = receipts["publish"]["tx_hash"]
            receipts["challenge"]["tx_hash"] = duplicate_hash
            artifact["challenge_tx_hash"] = duplicate_hash
        elif mutation == "invalidhash":
            receipts["publish"]["tx_hash"] = "not-a-transaction-hash"
        elif mutation == "mismatchpayout":
            payout["tx_hash"] = "0x" + "4" * 64

        artifacts.append(artifact)

    output = "TESTNET_AUDIT_ARTIFACTS=" + json.dumps(artifacts) + "\n"
    _fake_popen(monkeypatch, junit_xml=_junit_xml(), stdout=output)

    assert runner.main() == 1

    report = _read_report(configured_runner)
    assert report["status"] == "failed"
    assert expected_issue in "\n".join(report["issues"])


def test_startup_failure_writes_a_failed_report(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = "0xprivate-test-key-0123456789"

    def fail_start(*_args: object, **_kwargs: object) -> None:
        raise OSError(f"could not launch with {private_key}")

    monkeypatch.setattr(runner.subprocess, "Popen", fail_start)

    assert runner.main() == 1

    report = _read_report(configured_runner)
    assert report["status"] == "failed"
    assert any("Unable to start pytest" in issue for issue in report["issues"])
    assert (configured_runner / "smoke-report.md").exists()
    assert private_key not in (configured_runner / "pytest-output.log").read_text()


@pytest.mark.parametrize(
    "structured_line",
    [
        "TESTNET_CONTEXT_SUMMARY={broken",
        "TESTNET_CONTEXT_SUMMARY=[]",
    ],
    ids=["invalid-json", "invalid-shape"],
)
def test_malformed_structured_output_writes_a_failed_report(
    configured_runner: Path,
    monkeypatch: pytest.MonkeyPatch,
    structured_line: str,
) -> None:
    output = "\n".join(
        [
            structured_line,
            "TESTNET_AUDIT_ARTIFACTS=" + json.dumps([_hosted_artifact()]),
        ]
    ) + "\n"
    _fake_popen(monkeypatch, junit_xml=_junit_xml(), stdout=output)

    assert runner.main() == 1

    report = _read_report(configured_runner)
    assert report["status"] == "failed"
    assert any("TESTNET_CONTEXT_SUMMARY" in issue for issue in report["issues"])
    assert (configured_runner / "smoke-report.md").exists()
