from __future__ import annotations

from dataclasses import dataclass
import re

from proof_of_audit_agent.challenge_verifier import (
    ChallengeVerificationResult,
    EvidenceContext,
)
from proof_of_audit_agent.executable_evidence_runner import (
    ExecutableEvidenceRunResult,
    ExecutableEvidenceRunner,
)


VERIFIER_NAME = "executable-evidence-advisory-v1"
_COMMON_CALL_NAMES = {
    "assertEq",
    "assertTrue",
    "assertFalse",
    "deal",
    "expectRevert",
    "hoax",
    "label",
    "prank",
    "require",
    "skip",
    "startPrank",
    "stopPrank",
    "testFail",
    "vm",
}


@dataclass(frozen=True)
class FindingMatchAnalysis:
    matched_findings: list[str]
    unmatched_findings: list[str]


class ExecutableEvidenceVerifier:
    def __init__(
        self,
        runner: ExecutableEvidenceRunner | None = None,
    ) -> None:
        self.runner = runner or ExecutableEvidenceRunner()

    def verify(self, context: EvidenceContext) -> ChallengeVerificationResult:
        run_result = self.runner.run(context)
        if run_result.outcome == "invalid_evidence":
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="invalid_evidence",
                summary=run_result.summary,
                detail=run_result.detail,
                resolution="rejected",
                advisory_only=True,
                execution_log=run_result.execution_log or None,
            )
        if run_result.outcome == "runner_error":
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="verifier_unavailable",
                summary=run_result.summary,
                detail=run_result.detail,
                advisory_only=True,
                execution_log=run_result.execution_log or None,
            )

        analysis = self._match_findings(context, run_result)
        if run_result.outcome == "failed":
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="invalid_evidence",
                summary="Executable evidence did not reproduce the claimed exploit.",
                detail="The Foundry test failed or reverted against the pinned fork, so the submitted evidence does not currently support the challenge.",
                resolution="rejected",
                advisory_only=True,
                execution_log=run_result.execution_log or None,
                matched_findings=analysis.matched_findings,
                unmatched_findings=analysis.unmatched_findings,
            )
        if analysis.matched_findings:
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="verified",
                summary="Executable evidence reproduced behavior already covered by the published audit.",
                detail="The submitted test passes, but its demonstrated issue overlaps with the auditor's recorded findings, so the challenge should be rejected absent stronger contrary evidence.",
                resolution="rejected",
                advisory_only=True,
                execution_log=run_result.execution_log or None,
                matched_findings=analysis.matched_findings,
                unmatched_findings=analysis.unmatched_findings,
            )
        if analysis.unmatched_findings:
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="verified",
                summary="Executable evidence appears to demonstrate an issue not covered by the published audit.",
                detail="The submitted test passes on the pinned fork and the extracted issue signals do not match any recorded finding, so the challenge should be treated as advisory-upheld pending manual review.",
                resolution="upheld",
                advisory_only=True,
                execution_log=run_result.execution_log or None,
                matched_findings=analysis.matched_findings,
                unmatched_findings=analysis.unmatched_findings,
            )
        return ChallengeVerificationResult(
            verifier=VERIFIER_NAME,
            status="verifier_unavailable",
            summary="Executable evidence ran successfully but could not be matched to the published claim.",
            detail="Manual review is required because the advisory runner could not confidently determine whether the test demonstrates a new issue or one the audit already covered.",
            advisory_only=True,
            execution_log=run_result.execution_log or None,
        )

    def _match_findings(
        self, context: EvidenceContext, run_result: ExecutableEvidenceRunResult
    ) -> FindingMatchAnalysis:
        signals = self._extract_issue_signals(run_result)
        findings = context.published_report.get("findings")
        if not isinstance(findings, list):
            findings = []
        matched: list[str] = []
        remaining = set(signals)
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            if self._finding_matches_signals(finding, signals):
                finding_id = str(finding.get("finding_id") or finding.get("title") or "finding")
                matched.append(finding_id)
                remaining.difference_update(self._finding_tokens(finding))
        return FindingMatchAnalysis(
            matched_findings=matched,
            unmatched_findings=sorted(remaining),
        )

    def _extract_issue_signals(self, run_result: ExecutableEvidenceRunResult) -> set[str]:
        corpus = "\n".join(
            part
            for part in (
                run_result.source_text or "",
                run_result.stdout,
                run_result.stderr,
            )
            if part
        ).lower()
        signals: set[str] = set()
        keyword_map = {
            "reentrancy": "reentrancy",
            "rotateowner": "rotateowner",
            "withdraw": "withdraw",
            "emergencypayout": "emergencypayout",
            "setadmin": "setadmin",
            "admin": "admin",
            "owner": "owner",
            "unchecked": "unchecked",
            "external call": "external-call",
            "unauthorized": "unauthorized",
        }
        normalized = re.sub(r"[^a-z0-9]+", " ", corpus)
        compact = normalized.replace(" ", "")
        for needle, label in keyword_map.items():
            if needle.replace(" ", "") in compact:
                signals.add(label)
        source_text = run_result.source_text or ""
        for name in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", source_text):
            if name in _COMMON_CALL_NAMES or name.startswith("test"):
                continue
            signals.add(name.lower())
        return signals

    def _finding_matches_signals(self, finding: dict[str, object], signals: set[str]) -> bool:
        finding_tokens = self._finding_tokens(finding)
        return bool(finding_tokens & signals)

    def _finding_tokens(self, finding: dict[str, object]) -> set[str]:
        tokens: set[str] = set()
        for key in ("title", "description", "category", "detector", "affected_function"):
            value = finding.get(key)
            if not isinstance(value, str) or not value:
                continue
            normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
            compact = normalized.replace(" ", "")
            for token in normalized.split():
                if len(token) >= 4:
                    tokens.add(token)
            if compact:
                tokens.add(compact)
        return tokens
