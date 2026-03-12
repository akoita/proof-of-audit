from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class Finding:
    finding_id: str
    title: str
    severity: str
    category: str
    description: str
    impact: str
    recommendation: str
    detector: str
    confidence: str = "high"
    affected_function: str | None = None
    source_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    evidence_uri: str | None = None


@dataclass(frozen=True)
class AuditReport:
    benchmark_id: str
    contract_address: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    supported_checks: list[str] = field(
        default_factory=lambda: [
            "reentrancy",
            "access_control",
            "unchecked_external_call",
        ]
    )
    confidence: str = "high"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["report_hash"] = self.report_hash
        payload["metadata_hash"] = self.metadata_hash
        payload["max_severity"] = self.max_severity
        payload["finding_count"] = self.finding_count
        payload["severity_breakdown"] = self.severity_breakdown
        return payload

    @property
    def report_hash(self) -> str:
        return sha256(repr(asdict(self)).encode("utf-8")).hexdigest()

    @property
    def metadata_hash(self) -> str:
        return sha256(
            f"{self.benchmark_id}:{self.contract_address}:{len(self.findings)}".encode(
                "utf-8"
            )
        ).hexdigest()

    @property
    def max_severity(self) -> int:
        ranking = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        if not self.findings:
            return 0
        return max(ranking.get(finding.severity, 0) for finding in self.findings)

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def severity_breakdown(self) -> dict[str, int]:
        breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for finding in self.findings:
            breakdown[finding.severity] = breakdown.get(finding.severity, 0) + 1
        return breakdown
