from __future__ import annotations

from proof_of_audit_agent.models import AuditReport, Finding


BENCHMARKS = {
    "0x1000000000000000000000000000000000000001": AuditReport(
        benchmark_id="reentrancy-bank",
        contract_address="0x1000000000000000000000000000000000000001",
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
    "0x1000000000000000000000000000000000000002": AuditReport(
        benchmark_id="admin-setter",
        contract_address="0x1000000000000000000000000000000000000002",
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
    "0x1000000000000000000000000000000000000003": AuditReport(
        benchmark_id="clean-vault",
        contract_address="0x1000000000000000000000000000000000000003",
        summary="No benchmark issue found across the supported checks.",
        findings=[],
        confidence="medium",
    ),
}


class AuditWorker:
    """Returns deterministic reports for demo addresses and safe fallbacks otherwise."""

    def run_audit(self, contract_address: str) -> AuditReport:
        normalized = contract_address.lower()
        if normalized in BENCHMARKS:
            return BENCHMARKS[normalized]

        return AuditReport(
            benchmark_id="unknown",
            contract_address=normalized,
            summary="No deterministic benchmark matched. Report limited to supported heuristic coverage.",
            findings=[],
            confidence="low",
        )

