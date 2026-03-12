from proof_of_audit_agent.models import AuditReport, Finding


def test_report_serialization_includes_breakdown_and_rich_finding_metadata() -> None:
    report = AuditReport(
        benchmark_id="fixture",
        contract_address="0x1000000000000000000000000000000000000001",
        summary="Fixture summary",
        findings=[
            Finding(
                finding_id="fixture.issue-1",
                title="Issue 1",
                severity="high",
                category="access_control",
                description="Description",
                impact="Impact",
                recommendation="Recommendation",
                detector="pattern.access_control",
                affected_function="setOwner(address)",
                source_path="demo/contracts/Fixture.sol",
                start_line=10,
                end_line=12,
                evidence_uri="ipfs://fixture/issue-1",
            )
        ],
    )

    payload = report.to_dict()

    assert payload["finding_count"] == 1
    assert payload["severity_breakdown"]["high"] == 1
    assert payload["findings"][0]["finding_id"] == "fixture.issue-1"
    assert payload["findings"][0]["evidence_uri"] == "ipfs://fixture/issue-1"
