from __future__ import annotations

from dataclasses import dataclass
import re

from proof_of_audit_agent.challenge_verifier import (
    ChallengeVerificationResult,
    EvidenceContext,
    StructuredChallengeClaim,
    VerificationDossier,
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
        claim, signals = self._build_challenge_claim(run_result)
        if run_result.outcome == "invalid_evidence":
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="invalid_evidence",
                summary=run_result.summary,
                detail=run_result.detail,
                resolution="rejected",
                advisory_only=True,
                execution_log=run_result.execution_log or None,
                challenge_claim=claim,
                verification_dossier=self._build_dossier(
                    context=context,
                    run_result=run_result,
                    claim=claim,
                    comparison_status="not_assessed",
                    policy_status="rejected",
                    recommended_resolution="rejected",
                    matched_findings=[],
                    unmatched_signals=signals,
                    advisory_only=True,
                ),
            )
        if run_result.outcome == "runner_error":
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="verifier_unavailable",
                summary=run_result.summary,
                detail=run_result.detail,
                advisory_only=True,
                execution_log=run_result.execution_log or None,
                challenge_claim=claim,
                verification_dossier=self._build_dossier(
                    context=context,
                    run_result=run_result,
                    claim=claim,
                    comparison_status="not_assessed",
                    policy_status="manual_review_required",
                    recommended_resolution="manual_review_required",
                    matched_findings=[],
                    unmatched_signals=signals,
                    advisory_only=True,
                    abstained=True,
                ),
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
                challenge_claim=claim,
                verification_dossier=self._build_dossier(
                    context=context,
                    run_result=run_result,
                    claim=claim,
                    comparison_status="not_assessed",
                    policy_status="rejected",
                    recommended_resolution="rejected",
                    matched_findings=analysis.matched_findings,
                    unmatched_signals=analysis.unmatched_findings,
                    advisory_only=True,
                ),
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
                challenge_claim=claim,
                verification_dossier=self._build_dossier(
                    context=context,
                    run_result=run_result,
                    claim=claim,
                    comparison_status="already_covered",
                    policy_status="rejected",
                    recommended_resolution="rejected",
                    matched_findings=analysis.matched_findings,
                    unmatched_signals=analysis.unmatched_findings,
                    advisory_only=True,
                ),
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
                challenge_claim=claim,
                verification_dossier=self._build_dossier(
                    context=context,
                    run_result=run_result,
                    claim=claim,
                    comparison_status="likely_new_issue",
                    policy_status="manual_review_required",
                    recommended_resolution="upheld",
                    matched_findings=analysis.matched_findings,
                    unmatched_signals=analysis.unmatched_findings,
                    advisory_only=True,
                    abstained=True,
                ),
            )
        return ChallengeVerificationResult(
            verifier=VERIFIER_NAME,
            status="verifier_unavailable",
            summary="Executable evidence ran successfully but could not be matched to the published claim.",
            detail="Manual review is required because the advisory runner could not confidently determine whether the test demonstrates a new issue or one the audit already covered.",
            advisory_only=True,
            execution_log=run_result.execution_log or None,
            challenge_claim=claim,
            verification_dossier=self._build_dossier(
                context=context,
                run_result=run_result,
                claim=claim,
                comparison_status="ambiguous",
                policy_status="manual_review_required",
                recommended_resolution="manual_review_required",
                matched_findings=[],
                unmatched_signals=signals,
                advisory_only=True,
                abstained=True,
            ),
        )

    def _build_challenge_claim(
        self, run_result: ExecutableEvidenceRunResult
    ) -> tuple[StructuredChallengeClaim | None, list[str]]:
        signals = sorted(self._extract_issue_signals(run_result))
        if not signals:
            if not run_result.source_path and not run_result.source_text:
                return None, []
            return (
                StructuredChallengeClaim(
                    claim_type="generic_executable_claim",
                    basis="executable-evidence-runner",
                    confidence="low",
                    demonstrated_effect=run_result.summary,
                    claimed_impact=run_result.detail,
                ),
                [],
            )

        if "reentrancy" in signals:
            claim_type = "reentrancy"
            preconditions = ["attacker can trigger a re-entrant call path"]
            impact = "Potential balance drain or broken accounting through re-entry."
        elif {"rotateowner", "owner", "admin", "unauthorized"} & set(signals):
            claim_type = "access_control"
            preconditions = ["attacker can invoke a privileged code path without authorization"]
            impact = "Potential privilege escalation or unauthorized configuration changes."
        elif {"unchecked", "external-call"} & set(signals):
            claim_type = "unchecked_external_call"
            preconditions = ["the affected low-level call can fail during execution"]
            impact = "Potential silent failure or inconsistent accounting after an external call."
        else:
            claim_type = "generic_executable_claim"
            preconditions = []
            impact = run_result.detail

        affected_surfaces = [
            signal
            for signal in signals
            if signal not in {"reentrancy", "admin", "owner", "unauthorized", "unchecked", "external-call"}
        ]
        return (
            StructuredChallengeClaim(
                claim_type=claim_type,
                basis="executable-evidence-runner",
                confidence="medium",
                affected_surfaces=affected_surfaces,
                preconditions=preconditions,
                demonstrated_effect=run_result.summary,
                claimed_impact=impact,
                supporting_signals=signals,
            ),
            signals,
        )

    def _build_dossier(
        self,
        *,
        context: EvidenceContext,
        run_result: ExecutableEvidenceRunResult,
        claim: StructuredChallengeClaim | None,
        comparison_status: str,
        policy_status: str,
        recommended_resolution: str,
        matched_findings: list[str],
        unmatched_signals: list[str],
        advisory_only: bool,
        abstained: bool = False,
    ) -> VerificationDossier:
        integrity_status = "valid"
        if run_result.outcome == "invalid_evidence":
            integrity_status = "invalid"
        elif run_result.outcome == "runner_error":
            integrity_status = "unknown"

        execution_status = {
            "passed": "passed",
            "failed": "failed",
            "invalid_evidence": "not_executed",
            "runner_error": "runner_error",
        }.get(run_result.outcome, "unknown")

        return VerificationDossier(
            verifier_version=VERIFIER_NAME,
            evidence_type=context.evidence_type,
            integrity_status=integrity_status,
            execution_status=execution_status,
            comparison_status=comparison_status,
            policy_status=policy_status,
            advisory_only=advisory_only,
            challenge_claim=claim,
            matched_finding_ids=matched_findings,
            unmatched_signals=unmatched_signals,
            committed_evidence_hash=context.committed_evidence_hash,
            execution_env=context.execution_env,
            backend=run_result.backend,
            isolation_level=run_result.isolation_level,
            source_path=run_result.source_path,
            fork_block_number=run_result.fork_block_number,
            recommended_resolution=recommended_resolution,
            abstained=abstained,
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
