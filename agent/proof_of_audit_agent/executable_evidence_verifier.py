from __future__ import annotations

import re

from proof_of_audit_agent.challenge_verifier import (
    ChallengeVerificationResult,
    EvidenceContext,
    StructuredChallengeClaim,
    VerificationDossier,
)
from proof_of_audit_agent.challenge_claim_extractor import ChallengeClaimExtractor
from proof_of_audit_agent.executable_evidence_runner import (
    ExecutableEvidenceRunResult,
    ExecutableEvidenceRunner,
)
from proof_of_audit_agent.semantic_comparison import (
    AbstentionFirstPolicy,
    SemanticChallengeComparator,
    SemanticComparisonResult,
    SemanticPolicyDecision,
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


def _identifier_tokens(name: str) -> set[str]:
    cleaned = re.sub(r"^test", "", name)
    pieces = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    tokens = {
        token.lower()
        for token in re.split(r"[^A-Za-z0-9]+", pieces)
        if token and len(token) >= 4
    }
    compact = cleaned.lower()
    if compact:
        tokens.add(compact)
    return tokens


class ExecutableEvidenceVerifier:
    def __init__(
        self,
        runner: ExecutableEvidenceRunner | None = None,
        extractor: ChallengeClaimExtractor | None = None,
        comparator: SemanticChallengeComparator | None = None,
        policy: AbstentionFirstPolicy | None = None,
    ) -> None:
        self.runner = runner or ExecutableEvidenceRunner()
        self.extractor = extractor
        self.comparator = comparator or SemanticChallengeComparator()
        self.policy = policy or AbstentionFirstPolicy()

    def verify(self, context: EvidenceContext) -> ChallengeVerificationResult:
        run_result = self.runner.run(context)
        heuristic_claim, signals = self._build_challenge_claim(run_result)
        claim = heuristic_claim
        extraction_status = "not_attempted"
        extraction_detail: str | None = None
        model_metadata: dict[str, object] = {}
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
                    comparison_result=SemanticComparisonResult(
                        outcome="not_assessed",
                        confidence="unknown",
                        rationale="Evidence integrity validation failed before semantic comparison.",
                        unmatched_signals=signals,
                    ),
                    policy_decision=SemanticPolicyDecision(
                        status="rejected",
                        recommended_resolution="rejected",
                        abstained=False,
                        confidence="high",
                        rationale="Invalid executable evidence is rejected before semantic comparison.",
                    ),
                    policy_status="rejected",
                    recommended_resolution="rejected",
                    advisory_only=True,
                    model_metadata=model_metadata,
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
                    comparison_result=SemanticComparisonResult(
                        outcome="not_assessed",
                        confidence="unknown",
                        rationale="Semantic comparison could not run because the evidence runner failed.",
                        unmatched_signals=signals,
                    ),
                    policy_decision=SemanticPolicyDecision(
                        status="manual_review_required",
                        recommended_resolution="manual_review_required",
                        abstained=True,
                        confidence="unknown",
                        rationale="Runner failures require manual review.",
                    ),
                    policy_status="manual_review_required",
                    recommended_resolution="manual_review_required",
                    advisory_only=True,
                    abstained=True,
                    model_metadata=model_metadata,
                ),
            )

        if run_result.outcome == "passed" and self.extractor is not None:
            extraction = self.extractor.extract(context=context, run_result=run_result)
            extraction_status = extraction.status
            extraction_detail = extraction.detail
            model_metadata = dict(extraction.model_metadata)
            if extraction.claim is not None:
                claim = extraction.claim

            if extraction.status in {"invalid_output", "low_confidence", "extractor_error"}:
                summary = "Structured challenge claim extraction requires manual review."
                detail = extraction.detail or (
                    "The configured challenge claim extractor did not produce a usable high-confidence structured claim."
                )
                return ChallengeVerificationResult(
                    verifier=VERIFIER_NAME,
                    status="verifier_unavailable",
                    summary=summary,
                    detail=detail,
                    advisory_only=True,
                    execution_log=run_result.execution_log or None,
                    challenge_claim=claim,
                    verification_dossier=self._build_dossier(
                        context=context,
                        run_result=run_result,
                        claim=claim,
                        comparison_result=SemanticComparisonResult(
                            outcome="not_assessed",
                            confidence="unknown",
                            rationale="Semantic comparison was skipped because structured claim extraction did not produce a usable result.",
                            unmatched_signals=signals,
                        ),
                        policy_decision=SemanticPolicyDecision(
                            status="manual_review_required",
                            recommended_resolution="manual_review_required",
                            abstained=True,
                            confidence="unknown",
                            rationale=detail,
                        ),
                        policy_status="manual_review_required",
                        recommended_resolution="manual_review_required",
                        advisory_only=True,
                        abstained=True,
                        model_metadata=model_metadata,
                        extraction_status=extraction_status,
                        extraction_detail=extraction_detail,
                    ),
                )

        if run_result.outcome == "failed":
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="invalid_evidence",
                summary="Executable evidence did not reproduce the claimed exploit.",
                detail="The Foundry test failed or reverted against the pinned fork, so the submitted evidence does not currently support the challenge.",
                resolution="rejected",
                advisory_only=True,
                execution_log=run_result.execution_log or None,
                matched_findings=[],
                unmatched_findings=signals,
                challenge_claim=claim,
                verification_dossier=self._build_dossier(
                    context=context,
                    run_result=run_result,
                    claim=claim,
                    comparison_result=SemanticComparisonResult(
                        outcome="not_assessed",
                        confidence="unknown",
                        rationale="The exploit did not reproduce, so semantic comparison was skipped.",
                        unmatched_signals=signals,
                    ),
                    policy_decision=SemanticPolicyDecision(
                        status="rejected",
                        recommended_resolution="rejected",
                        abstained=False,
                        confidence="high",
                        rationale="Failed executable evidence is rejected without semantic comparison.",
                    ),
                    policy_status="rejected",
                    recommended_resolution="rejected",
                    advisory_only=True,
                    model_metadata=model_metadata,
                    extraction_status=extraction_status,
                    extraction_detail=extraction_detail,
                ),
            )

        comparison = self.comparator.compare(
            claim=claim,
            published_report=context.published_report,
        )
        policy = self.policy.decide(comparison)

        if comparison.outcome == "already_covered" and not policy.abstained:
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="verified",
                summary="Executable evidence reproduced behavior already covered by the published audit.",
                detail=comparison.rationale,
                resolution="rejected",
                advisory_only=True,
                execution_log=run_result.execution_log or None,
                matched_findings=comparison.matched_finding_ids,
                unmatched_findings=comparison.unmatched_signals,
                challenge_claim=claim,
                verification_dossier=self._build_dossier(
                    context=context,
                    run_result=run_result,
                    claim=claim,
                    comparison_result=comparison,
                    policy_decision=policy,
                    policy_status=policy.status,
                    recommended_resolution=policy.recommended_resolution,
                    advisory_only=True,
                    model_metadata=model_metadata,
                    extraction_status=extraction_status,
                    extraction_detail=extraction_detail,
                ),
            )

        if comparison.outcome in {"likely_new_issue", "contradicts_audit_claim"}:
            return ChallengeVerificationResult(
                verifier=VERIFIER_NAME,
                status="verified",
                summary=(
                    "Executable evidence appears to demonstrate an issue not covered by the published audit."
                    if comparison.outcome == "likely_new_issue"
                    else "Executable evidence appears to contradict the published audit claim."
                ),
                detail=comparison.rationale,
                resolution="upheld",
                advisory_only=True,
                execution_log=run_result.execution_log or None,
                matched_findings=comparison.matched_finding_ids,
                unmatched_findings=comparison.unmatched_signals,
                challenge_claim=claim,
                verification_dossier=self._build_dossier(
                    context=context,
                    run_result=run_result,
                    claim=claim,
                    comparison_result=comparison,
                    policy_decision=policy,
                    policy_status=policy.status,
                    recommended_resolution=policy.recommended_resolution,
                    advisory_only=True,
                    abstained=policy.abstained,
                    model_metadata=model_metadata,
                    extraction_status=extraction_status,
                    extraction_detail=extraction_detail,
                ),
            )
        return ChallengeVerificationResult(
            verifier=VERIFIER_NAME,
            status="verifier_unavailable",
            summary=(
                "Executable evidence ran successfully but requires manual semantic review."
            ),
            detail=policy.rationale,
            advisory_only=True,
            execution_log=run_result.execution_log or None,
            challenge_claim=claim,
            verification_dossier=self._build_dossier(
                context=context,
                run_result=run_result,
                claim=claim,
                comparison_result=comparison,
                policy_decision=policy,
                policy_status=policy.status,
                recommended_resolution=policy.recommended_resolution,
                advisory_only=True,
                abstained=policy.abstained,
                model_metadata=model_metadata,
                extraction_status=extraction_status,
                extraction_detail=extraction_detail,
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
        elif {"rotateowner", "owner", "admin", "unauthorized", "privilege", "takeover"} & set(signals):
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
        comparison_result: SemanticComparisonResult,
        policy_decision: SemanticPolicyDecision,
        policy_status: str,
        recommended_resolution: str,
        advisory_only: bool,
        abstained: bool = False,
        model_metadata: dict[str, object] | None = None,
        extraction_status: str | None = None,
        extraction_detail: str | None = None,
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
            comparison_status=comparison_result.outcome,
            policy_status=policy_status,
            advisory_only=advisory_only,
            challenge_claim=claim,
            matched_finding_ids=comparison_result.matched_finding_ids,
            matched_findings=comparison_result.matched_findings,
            unmatched_signals=comparison_result.unmatched_signals,
            comparison_confidence=comparison_result.confidence,
            comparison_rationale=comparison_result.rationale,
            disagreement_status=comparison_result.disagreement_status,
            disagreement_detail=comparison_result.disagreement_detail,
            committed_evidence_hash=context.committed_evidence_hash,
            execution_env=context.execution_env,
            backend=run_result.backend,
            isolation_level=run_result.isolation_level,
            source_path=run_result.source_path,
            fork_block_number=run_result.fork_block_number,
            recommended_resolution=recommended_resolution,
            abstained=abstained,
            policy_confidence=policy_decision.confidence,
            policy_rationale=policy_decision.rationale,
            model_metadata={
                **(model_metadata or {}),
                **(
                    {"extraction_status": extraction_status}
                    if extraction_status is not None
                    else {}
                ),
                **(
                    {"extraction_detail": extraction_detail}
                    if extraction_detail
                    else {}
                ),
            },
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
            "privilege": "privilege",
            "takeover": "takeover",
        }
        normalized = re.sub(r"[^a-z0-9]+", " ", corpus)
        compact = normalized.replace(" ", "")
        for needle, label in keyword_map.items():
            if needle.replace(" ", "") in compact:
                signals.add(label)
        source_text = run_result.source_text or ""
        for name in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", source_text):
            if name in _COMMON_CALL_NAMES:
                continue
            signals.update(_identifier_tokens(name))
        return signals
