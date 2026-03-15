from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from proof_of_audit_agent.agent_forge_backend import (
    AgentForgeExecutionError,
    AuditExecutionResult,
    AgentForgeBackend,
)
from proof_of_audit_agent.fixtures import DemoFixture, load_demo_fixtures
from proof_of_audit_agent.models import AuditReport, Finding
from proof_of_audit_agent.runtime import WorkerRuntimeConfig


BENCHMARK_REPORTS = {
    "reentrancy-bank": AuditReport(
        benchmark_id="reentrancy-bank",
        contract_address="0x0000000000000000000000000000000000000000",
        summary="Withdraw updates balance after the external call, enabling recursive drains.",
        findings=[
            Finding(
                finding_id="reentrancy-bank.withdraw.reentrancy",
                title="Reentrancy in withdraw()",
                severity="high",
                category="reentrancy",
                description="ETH is sent to msg.sender before internal accounting is updated.",
                impact="An attacker can recursively drain balances before their accounting is reduced.",
                recommendation="Apply checks-effects-interactions or a reentrancy guard.",
                detector="pattern.reentrancy",
                affected_function="withdraw(uint256)",
                source_path="demo/contracts/VulnerableBank.sol",
                start_line=10,
                end_line=13,
                evidence_uri="ipfs://reentrancy-bank/withdraw-drain",
            )
        ],
    ),
    "admin-setter": AuditReport(
        benchmark_id="admin-setter",
        contract_address="0x0000000000000000000000000000000000000000",
        summary="Privileged configuration can be changed by any caller.",
        findings=[
            Finding(
                finding_id="admin-setter.set-admin.missing-access-control",
                title="Missing access control on setAdmin()",
                severity="high",
                category="access_control",
                description="The function updates the admin role without checking ownership.",
                impact="Any account can seize privileged control of the contract.",
                recommendation="Restrict the function with onlyOwner or equivalent role checks.",
                detector="pattern.access_control",
                affected_function="setAdmin(address)",
                source_path="demo/contracts/AdminSetter.sol",
                start_line=7,
                end_line=9,
                evidence_uri="ipfs://admin-setter/unauthorized-admin-change",
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
                finding_id="unchecked-treasury.pay-module.unchecked-call",
                title="Unchecked external call in payModule()",
                severity="medium",
                category="unchecked_external_call",
                description="The treasury performs a low-level call without checking the success flag.",
                impact="Payment failures can be silently ignored and downstream accounting can drift from reality.",
                recommendation="Check the returned boolean and revert or handle the failure path explicitly.",
                detector="pattern.unchecked_external_call",
                confidence="medium",
                affected_function="payModule(address,uint256)",
                source_path="demo/contracts/UncheckedTreasury.sol",
                start_line=9,
                end_line=12,
                evidence_uri="ipfs://unchecked-treasury/unchecked-call-failure",
            )
        ],
        confidence="medium",
    ),
    "dual-risk-vault": AuditReport(
        benchmark_id="dual-risk-vault",
        contract_address="0x0000000000000000000000000000000000000000",
        summary="The vault exposes both unrestricted role rotation and unchecked emergency payouts.",
        findings=[
            Finding(
                finding_id="dual-risk-vault.rotate-owner.missing-access-control",
                title="Missing access control on rotateOwner()",
                severity="high",
                category="access_control",
                description="Ownership can be reassigned by any caller without authorization.",
                impact="An attacker can seize control of privileged payout operations.",
                recommendation="Restrict ownership changes to the current owner or a governed admin path.",
                detector="pattern.access_control",
                affected_function="rotateOwner(address)",
                source_path="demo/contracts/DualRiskVault.sol",
                start_line=15,
                end_line=17,
                evidence_uri="ipfs://dual-risk-vault/owner-takeover",
            ),
            Finding(
                finding_id="dual-risk-vault.emergency-payout.unchecked-call",
                title="Unchecked external call in emergencyPayout()",
                severity="medium",
                category="unchecked_external_call",
                description="The emergency payout path ignores the success flag from a low-level call.",
                impact="Failed emergency payouts may be reported as successful, leaving funds stranded or accounting inconsistent.",
                recommendation="Check the return value and revert or emit a failure path when the payout fails.",
                detector="pattern.unchecked_external_call",
                confidence="medium",
                affected_function="emergencyPayout(uint256)",
                source_path="demo/contracts/DualRiskVault.sol",
                start_line=19,
                end_line=22,
                evidence_uri="ipfs://dual-risk-vault/emergency-payout-failure",
            ),
        ],
        confidence="medium",
    ),
}

LEGACY_BENCHMARK_ADDRESSES = {
    "0x1000000000000000000000000000000000000001": "reentrancy-bank",
    "0x1000000000000000000000000000000000000002": "admin-setter",
    "0x1000000000000000000000000000000000000003": "clean-vault",
    "0x1000000000000000000000000000000000000004": "dual-risk-vault",
}


class AuditWorker:
    """Returns deterministic reports for demo addresses and safe fallbacks otherwise."""

    def __init__(
        self,
        fixtures_file: Path | None = None,
        *,
        runtime: WorkerRuntimeConfig | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.fixtures = load_demo_fixtures(fixtures_file)
        self.runtime = runtime or WorkerRuntimeConfig()
        self.workspace_root = workspace_root or Path.cwd() / ".proof-of-audit-runtime"
        self._fixtures_by_address = {
            fixture.address: fixture for fixture in self.fixtures
        }
        self._fixtures_by_id = {
            fixture.fixture_id: fixture for fixture in self.fixtures
        }
        self.agent_forge = AgentForgeBackend(self.runtime.agent_forge, self.workspace_root)

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

    def run_submission(
        self,
        *,
        audit_id: str | None = None,
        input_kind: str,
        chain_id: int | None = None,
        contract_address: str | None = None,
        fixture_id: str | None = None,
        entry_contract: str | None = None,
        source_bundle_uri: str | None = None,
        source_bundle_label: str | None = None,
        repository_url: str | None = None,
    ) -> AuditExecutionResult:
        del chain_id, source_bundle_label
        live_attempted = False
        if input_kind == "demo_fixture":
            return AuditExecutionResult(
                report=self._report_for_fixture(self.require_fixture(fixture_id))
            )

        if input_kind == "source_bundle":
            if audit_id is not None:
                live_attempted = True
                live_result = self.agent_forge.run_submission(
                    audit_id=audit_id,
                    input_kind=input_kind,
                    source_bundle_uri=source_bundle_uri,
                    entry_contract=entry_contract,
                )
                if live_result is not None:
                    return live_result
            source_identifier = self.synthetic_contract_address(
                source_bundle_uri or "source-bundle",
                entry_contract=entry_contract,
            )
            benchmark_id = self._infer_source_bundle_benchmark(
                entry_contract=entry_contract,
                source_bundle_uri=source_bundle_uri,
            )
            if benchmark_id is not None:
                return AuditExecutionResult(
                    report=self._report_for_benchmark_id(benchmark_id, source_identifier),
                    execution=self.agent_forge.fallback_execution(
                        reason="No live agent-forge execution was available for this source bundle. Returned the deterministic benchmark mapping instead.",
                        live_attempted=live_attempted,
                        source="deterministic-benchmark",
                    ),
                )
            return AuditExecutionResult(
                report=AuditReport(
                    benchmark_id="source-bundle",
                    contract_address=source_identifier,
                    summary="Source bundle received. No deterministic benchmark matched the supplied entry contract or bundle metadata.",
                    findings=[],
                    confidence="low",
                ),
                execution=self.agent_forge.fallback_execution(
                    reason="No deterministic benchmark matched this source bundle and no live agent-forge execution result was produced.",
                    live_attempted=live_attempted,
                    source="safe-fallback",
                ),
            )

        if input_kind == "repository_url":
            if audit_id is None:
                raise ValueError("audit_id is required for repository_url submissions")
            live_attempted = True
            try:
                live_result = self.agent_forge.run_submission(
                    audit_id=audit_id,
                    input_kind=input_kind,
                    repository_url=repository_url,
                    entry_contract=entry_contract,
                )
            except AgentForgeExecutionError:
                raise
            if live_result is not None:
                return live_result
            if self.runtime.mode == "agent_forge":
                raise AgentForgeExecutionError(
                    "repository_url submissions require a local repository path or file:// URL when worker mode is agent_forge"
                )
            synthetic_address = self.synthetic_contract_address(
                repository_url or "repository-url",
                entry_contract=entry_contract,
            )
            return AuditExecutionResult(
                report=AuditReport(
                    benchmark_id="repository-url",
                    contract_address=synthetic_address,
                    summary="Repository submission received, but the worker fell back because no local agent-forge execution path was available.",
                    findings=[],
                    confidence="low",
                ),
                execution=self.agent_forge.fallback_execution(
                    reason="Repository submissions use the live agent-forge path only when a local repository checkout is available.",
                    live_attempted=live_attempted,
                    source="safe-fallback",
                ),
            )

        if contract_address is None:
            raise ValueError("contract_address is required for deployed address submissions")
        return AuditExecutionResult(report=self.run_audit(contract_address))

    def require_fixture(self, fixture_id: str | None) -> DemoFixture:
        if fixture_id is None or fixture_id not in self._fixtures_by_id:
            raise ValueError("unknown demo fixture")
        return self._fixtures_by_id[fixture_id]

    def synthetic_contract_address(
        self, source_bundle_uri: str, entry_contract: str | None = None
    ) -> str:
        digest = sha256(
            f"{source_bundle_uri}:{entry_contract or ''}".encode("utf-8")
        ).hexdigest()
        return f"0x{digest[:40]}"

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

    def _infer_source_bundle_benchmark(
        self, *, entry_contract: str | None, source_bundle_uri: str | None
    ) -> str | None:
        haystack = " ".join(
            part.lower()
            for part in [entry_contract or "", source_bundle_uri or ""]
            if part
        )
        if "dualriskvault" in haystack or "dual-risk-vault" in haystack:
            return "dual-risk-vault"
        if "cleanvault" in haystack or "clean-vault" in haystack:
            return "clean-vault"
        if "vulnerablebank" in haystack or "reentrancy-bank" in haystack:
            return "reentrancy-bank"
        if "adminsetter" in haystack or "admin-setter" in haystack:
            return "admin-setter"
        if "uncheckedtreasury" in haystack or "unchecked-treasury" in haystack:
            return "unchecked-treasury"
        return None
