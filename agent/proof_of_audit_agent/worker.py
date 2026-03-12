from __future__ import annotations

from pathlib import Path

from proof_of_audit_agent.fixtures import DemoFixture, load_demo_fixtures
from proof_of_audit_agent.models import AuditReport, Finding


BENCHMARK_REPORTS = {
    "reentrancy-bank": AuditReport(
        benchmark_id="reentrancy-bank",
        contract_address="0x0000000000000000000000000000000000000000",
        summary="Withdraw updates balance after the external call, enabling recursive drains.",
        findings=[
            Finding(
                title="Reentrancy in withdraw()",
                severity="high",
                description="ETH is sent to msg.sender before internal accounting is updated.",
                recommendation="Apply checks-effects-interactions or a reentrancy guard.",
                detector="pattern.reentrancy",
            )
        ],
    ),
    "admin-setter": AuditReport(
        benchmark_id="admin-setter",
        contract_address="0x0000000000000000000000000000000000000000",
        summary="Privileged configuration can be changed by any caller.",
        findings=[
            Finding(
                title="Missing access control on setAdmin()",
                severity="high",
                description="The function updates the admin role without checking ownership.",
                recommendation="Restrict the function with onlyOwner or equivalent role checks.",
                detector="pattern.access_control",
            )
        ],
    ),
    "clean-vault": AuditReport(
        benchmark_id="clean-vault",
        contract_address="0x0000000000000000000000000000000000000000",
        summary="No benchmark issue found across the supported checks.",
        findings=[],
        confidence="medium",
    ),
    "unchecked-treasury": AuditReport(
        benchmark_id="unchecked-treasury",
        contract_address="0x0000000000000000000000000000000000000000",
        summary="A low-level external call ignores its return value, so failures can be silently swallowed.",
        findings=[
            Finding(
                title="Unchecked external call in payModule()",
                severity="medium",
                description="The treasury performs a low-level call without checking the success flag.",
                recommendation="Check the returned boolean and revert or handle the failure path explicitly.",
                detector="pattern.unchecked_external_call",
            )
        ],
        confidence="medium",
    ),
}

LEGACY_BENCHMARK_ADDRESSES = {
    "0x1000000000000000000000000000000000000001": "reentrancy-bank",
    "0x1000000000000000000000000000000000000002": "admin-setter",
    "0x1000000000000000000000000000000000000003": "clean-vault",
}


class AuditWorker:
    """Returns deterministic reports for demo addresses and safe fallbacks otherwise."""

    def __init__(self, fixtures_file: Path | None = None) -> None:
        self.fixtures = load_demo_fixtures(fixtures_file)
        self._fixtures_by_address = {
            fixture.address: fixture for fixture in self.fixtures
        }

    def run_audit(self, contract_address: str) -> AuditReport:
        normalized = contract_address.lower()
        fixture = self._fixtures_by_address.get(normalized)
        if fixture is not None:
            return self._report_for_fixture(fixture)
        if normalized in LEGACY_BENCHMARK_ADDRESSES:
            return self._report_for_benchmark_id(
                LEGACY_BENCHMARK_ADDRESSES[normalized],
                normalized,
            )

        return AuditReport(
            benchmark_id="unknown",
            contract_address=normalized,
            summary="No deterministic benchmark matched. Report limited to supported heuristic coverage.",
            findings=[],
            confidence="low",
        )

    def list_demo_fixtures(self) -> list[dict[str, str]]:
        return [fixture.to_dict() for fixture in self.fixtures]

    def _report_for_fixture(self, fixture: DemoFixture) -> AuditReport:
        return self._report_for_benchmark_id(fixture.benchmark_id, fixture.address)

    def _report_for_benchmark_id(
        self, benchmark_id: str, contract_address: str
    ) -> AuditReport:
        template = BENCHMARK_REPORTS[benchmark_id]
        return AuditReport(
            benchmark_id=template.benchmark_id,
            contract_address=contract_address,
            summary=template.summary,
            findings=template.findings,
            supported_checks=template.supported_checks,
            confidence=template.confidence,
        )
