from proof_of_audit_agent.challenge_verifier import EvidenceContext
from proof_of_audit_agent.executable_evidence_runner import ExecutableEvidenceRunResult
from proof_of_audit_agent.executable_evidence_verifier import ExecutableEvidenceVerifier
from proof_of_audit_agent.challenge_claim_extractor import (
    ChallengeClaimExtractionResult,
)
from proof_of_audit_agent.challenge_verifier import StructuredChallengeClaim


class StubRunner:
    def __init__(self, result: ExecutableEvidenceRunResult) -> None:
        self.result = result

    def run(self, context: EvidenceContext) -> ExecutableEvidenceRunResult:
        return self.result


class StubExtractor:
    def __init__(self, result: ChallengeClaimExtractionResult) -> None:
        self.result = result
        self.calls = 0

    def extract(
        self,
        *,
        context: EvidenceContext,
        run_result: ExecutableEvidenceRunResult,
    ) -> ChallengeClaimExtractionResult:
        del context, run_result
        self.calls += 1
        return self.result


def _context() -> EvidenceContext:
    return EvidenceContext(
        proof_uri="file:///tmp/ChallengeEvidence.t.sol",
        benchmark_id="reentrancy-bank",
        target_contract="0x1000000000000000000000000000000000000001",
        published_report={
            "findings": [
                {
                    "finding_id": "finding-1",
                    "title": "Reentrancy in withdraw()",
                    "category": "reentrancy",
                    "description": "withdraw sends ETH before updating balance",
                    "affected_function": "withdraw",
                }
            ]
        },
        evidence_type="executable_test",
        execution_env="foundry",
        evidence_manifest={
            "bundle_format": "proof-of-audit-executable-evidence/v1",
            "execution_env": "foundry",
            "entrypoint": "ChallengeEvidence.t.sol",
            "target_chain_id": 31337,
        },
        chain_id=31337,
        rpc_url="http://127.0.0.1:8545",
    )


def test_executable_evidence_matching_reported_issue_is_advisory_rejected() -> None:
    verifier = ExecutableEvidenceVerifier(
        runner=StubRunner(
            ExecutableEvidenceRunResult(
                outcome="passed",
                summary="passed",
                detail="passed",
                source_text="contract ChallengeTest { function test_withdraw_reentrancy() public {} }",
                stdout="withdraw reentrancy reproduced",
            )
        )
    )

    result = verifier.verify(_context())

    assert result.status == "verified"
    assert result.resolution == "rejected"
    assert result.advisory_only is True
    assert result.matched_findings == ["finding-1"]
    assert result.challenge_claim is not None
    assert result.challenge_claim.claim_type == "reentrancy"
    assert result.verification_dossier is not None
    assert result.verification_dossier.comparison_status == "already_covered"
    assert result.verification_dossier.comparison_confidence in {"medium", "high"}
    assert result.verification_dossier.matched_findings[0].relationship == "already_covered"
    assert result.verification_dossier.policy_rationale is not None


def test_executable_evidence_new_issue_is_advisory_upheld() -> None:
    verifier = ExecutableEvidenceVerifier(
        runner=StubRunner(
            ExecutableEvidenceRunResult(
                outcome="passed",
                summary="passed",
                detail="passed",
                source_text="contract ChallengeTest { function test_rotateOwner_takeover() public {} }",
                stdout="rotateOwner owner takeover reproduced",
            )
        )
    )

    result = verifier.verify(_context())

    assert result.status == "verified"
    assert result.resolution == "upheld"
    assert result.advisory_only is True
    assert "rotateowner" in result.unmatched_findings
    assert result.challenge_claim is not None
    assert result.challenge_claim.claim_type == "access_control"
    assert result.verification_dossier is not None
    assert result.verification_dossier.comparison_status == "likely_new_issue"
    assert result.verification_dossier.policy_status == "manual_review_required"
    assert result.verification_dossier.policy_confidence in {"medium", "high"}


def test_executable_evidence_failed_run_is_invalid_evidence() -> None:
    verifier = ExecutableEvidenceVerifier(
        runner=StubRunner(
            ExecutableEvidenceRunResult(
                outcome="failed",
                summary="failed",
                detail="failed",
                stderr="forge test failed",
            )
        )
    )

    result = verifier.verify(_context())

    assert result.status == "invalid_evidence"
    assert result.resolution == "rejected"
    assert result.advisory_only is True
    assert result.verification_dossier is not None
    assert result.verification_dossier.execution_status == "failed"


def test_executable_evidence_clean_report_is_contradictory_upheld() -> None:
    context = EvidenceContext(
        proof_uri="file:///tmp/ChallengeEvidence.t.sol",
        benchmark_id="clean-vault",
        target_contract="0x1000000000000000000000000000000000000001",
        published_report={
            "summary": "Clean audit report with no findings.",
            "findings": [],
            "normalized_findings": [],
        },
        evidence_type="executable_test",
        execution_env="foundry",
        evidence_manifest={
            "bundle_format": "proof-of-audit-executable-evidence/v1",
            "execution_env": "foundry",
            "entrypoint": "ChallengeEvidence.t.sol",
            "target_chain_id": 31337,
        },
        chain_id=31337,
        rpc_url="http://127.0.0.1:8545",
    )
    verifier = ExecutableEvidenceVerifier(
        runner=StubRunner(
            ExecutableEvidenceRunResult(
                outcome="passed",
                summary="ownership changes without authorization",
                detail="passed",
                source_text="contract ChallengeTest { function test_rotateOwner_takeover() public {} }",
                stdout="rotateOwner owner takeover reproduced",
            )
        )
    )

    result = verifier.verify(context)

    assert result.status == "verified"
    assert result.resolution == "upheld"
    assert result.verification_dossier is not None
    assert result.verification_dossier.comparison_status == "contradicts_audit_claim"
    assert result.verification_dossier.policy_status == "manual_review_required"


def test_executable_evidence_same_root_cause_variant_abstains() -> None:
    verifier = ExecutableEvidenceVerifier(
        runner=StubRunner(
            ExecutableEvidenceRunResult(
                outcome="passed",
                summary="passed",
                detail="passed",
                source_text="contract ChallengeTest { function test_deposit_reentrancy_variant() public {} }",
                stdout="deposit reentrancy reproduced",
            )
        )
    )

    result = verifier.verify(_context())

    assert result.status == "verifier_unavailable"
    assert result.resolution is None
    assert result.verification_dossier is not None
    assert result.verification_dossier.comparison_status == "same_root_cause_variant"
    assert result.verification_dossier.policy_status == "manual_review_required"
    assert result.verification_dossier.abstained is True


def test_executable_evidence_uses_high_confidence_extractor_claim() -> None:
    extractor = StubExtractor(
        ChallengeClaimExtractionResult(
            status="complete",
            claim=StructuredChallengeClaim(
                claim_type="access_control",
                basis="llm_command_extractor",
                confidence="high",
                affected_surfaces=["rotateOwner"],
                preconditions=["arbitrary caller"],
                demonstrated_effect="ownership changes without authorization",
                claimed_impact="privilege takeover",
                supporting_signals=["rotateowner", "owner", "unauthorized"],
            ),
            model_metadata={
                "provider": "openai",
                "model": "gpt-5.4-mini",
                "prompt_version": "challenge-claim-extractor/v1",
            },
        )
    )
    verifier = ExecutableEvidenceVerifier(
        runner=StubRunner(
            ExecutableEvidenceRunResult(
                outcome="passed",
                summary="passed",
                detail="passed",
                source_text="contract ChallengeTest { function test_rotateOwner_takeover() public {} }",
                stdout="rotateOwner owner takeover reproduced",
            )
        ),
        extractor=extractor,
    )

    result = verifier.verify(_context())

    assert extractor.calls == 1
    assert result.challenge_claim is not None
    assert result.challenge_claim.basis == "llm_command_extractor"
    assert result.verification_dossier is not None
    assert result.verification_dossier.model_metadata["provider"] == "openai"
    assert result.verification_dossier.model_metadata["extraction_status"] == "complete"
    assert result.verification_dossier.comparison_status == "likely_new_issue"


def test_low_confidence_extractor_forces_manual_review() -> None:
    verifier = ExecutableEvidenceVerifier(
        runner=StubRunner(
            ExecutableEvidenceRunResult(
                outcome="passed",
                summary="passed",
                detail="passed",
                source_text="contract ChallengeTest { function test_rotateOwner_takeover() public {} }",
                stdout="rotateOwner owner takeover reproduced",
            )
        ),
        extractor=StubExtractor(
            ChallengeClaimExtractionResult(
                status="low_confidence",
                claim=StructuredChallengeClaim(
                    claim_type="access_control",
                    basis="llm_command_extractor",
                    confidence="low",
                ),
                detail="low confidence",
                model_metadata={"provider": "openai", "model": "gpt-5.4-mini"},
            )
        ),
    )

    result = verifier.verify(_context())

    assert result.status == "verifier_unavailable"
    assert result.challenge_claim is not None
    assert result.challenge_claim.confidence == "low"
    assert result.verification_dossier is not None
    assert result.verification_dossier.policy_status == "manual_review_required"
    assert result.verification_dossier.model_metadata["extraction_status"] == "low_confidence"
