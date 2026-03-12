import json

from proof_of_audit_agent.worker import AuditWorker


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
