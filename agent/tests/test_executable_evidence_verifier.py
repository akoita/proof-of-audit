from proof_of_audit_agent.challenge_verifier import EvidenceContext
from proof_of_audit_agent.executable_evidence_runner import ExecutableEvidenceRunResult
from proof_of_audit_agent.executable_evidence_verifier import ExecutableEvidenceVerifier


class StubRunner:
    def __init__(self, result: ExecutableEvidenceRunResult) -> None:
        self.result = result

    def run(self, context: EvidenceContext) -> ExecutableEvidenceRunResult:
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
