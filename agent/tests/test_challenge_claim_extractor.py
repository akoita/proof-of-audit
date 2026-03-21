import json
from pathlib import Path
import tempfile
import unittest

from proof_of_audit_agent.challenge_claim_extractor import (
    CommandBackedChallengeClaimExtractor,
)
from proof_of_audit_agent.challenge_verifier import EvidenceContext
from proof_of_audit_agent.executable_evidence_runner import ExecutableEvidenceRunResult


class CommandBackedChallengeClaimExtractorTest(unittest.TestCase):
    def _context(self) -> EvidenceContext:
        return EvidenceContext(
            proof_uri="file:///tmp/ChallengeEvidence.t.sol",
            benchmark_id="dual-risk-vault",
            target_contract="0x1000000000000000000000000000000000000001",
            published_report={
                "summary": "audit summary",
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

    def _run_result(self) -> ExecutableEvidenceRunResult:
        return ExecutableEvidenceRunResult(
            outcome="passed",
            summary="Executable evidence passed against the forked chain state.",
            detail="Foundry reported a successful test run for the submitted evidence.",
            stdout="rotateOwner owner takeover reproduced",
            source_text="contract ChallengeTest { function test_rotateOwner_takeover() public {} }",
            backend="local_subprocess",
            isolation_level="process",
            source_path="/tmp/ChallengeEvidence.t.sol",
            fork_block_number=42,
        )

    def test_command_extractor_returns_structured_claim_and_model_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "extractor.py"
            script.write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "payload = json.load(sys.stdin)",
                        "assert payload['challenge']['execution_env'] == 'foundry'",
                        "json.dump({",
                        "  'claim': {",
                        "    'claim_type': 'access_control',",
                        "    'basis': 'llm_command_extractor',",
                        "    'confidence': 'high',",
                        "    'affected_surfaces': ['rotateOwner'],",
                        "    'preconditions': ['arbitrary caller'],",
                        "    'demonstrated_effect': 'ownership changes without authorization',",
                        "    'claimed_impact': 'privilege takeover',",
                        "    'supporting_signals': ['rotateowner', 'owner', 'unauthorized']",
                        "  },",
                        "  'model_metadata': {",
                        "    'provider': 'openai',",
                        "    'model': 'gpt-5.4-mini',",
                        "    'prompt_version': 'challenge-claim-extractor/v1'",
                        "  }",
                        "}, sys.stdout)",
                    ]
                ),
                encoding="utf-8",
            )
            extractor = CommandBackedChallengeClaimExtractor(
                command=f"python3 {script}",
                provider="openai",
                model="gpt-5.4-mini",
            )

            result = extractor.extract(context=self._context(), run_result=self._run_result())

            self.assertEqual(result.status, "complete")
            self.assertIsNotNone(result.claim)
            self.assertEqual(result.claim.claim_type, "access_control")
            self.assertEqual(result.model_metadata["provider"], "openai")
            self.assertEqual(result.model_metadata["model"], "gpt-5.4-mini")
            self.assertEqual(
                result.model_metadata["prompt_version"],
                "challenge-claim-extractor/v1",
            )

    def test_command_extractor_rejects_low_confidence_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "extractor.py"
            script.write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "json.dump({",
                        "  'claim': {",
                        "    'claim_type': 'access_control',",
                        "    'basis': 'llm_command_extractor',",
                        "    'confidence': 'low'",
                        "  },",
                        "  'model_metadata': {'provider': 'openai', 'model': 'gpt-5.4-mini'}",
                        "}, sys.stdout)",
                    ]
                ),
                encoding="utf-8",
            )
            extractor = CommandBackedChallengeClaimExtractor(
                command=f"python3 {script}",
                provider="openai",
                model="gpt-5.4-mini",
                min_confidence="medium",
            )

            result = extractor.extract(context=self._context(), run_result=self._run_result())

            self.assertEqual(result.status, "low_confidence")
            self.assertIsNotNone(result.claim)
            self.assertEqual(result.claim.confidence, "low")

    def test_command_extractor_rejects_malformed_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "extractor.py"
            script.write_text("print('not-json')\n", encoding="utf-8")
            extractor = CommandBackedChallengeClaimExtractor(
                command=f"python3 {script}",
                provider="openai",
                model="gpt-5.4-mini",
            )

            result = extractor.extract(context=self._context(), run_result=self._run_result())

            self.assertEqual(result.status, "invalid_output")
            self.assertIn("valid JSON", result.detail)
