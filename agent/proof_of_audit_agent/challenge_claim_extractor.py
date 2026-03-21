from __future__ import annotations

from dataclasses import dataclass, field
import json
import shlex
import subprocess
from typing import Any, Protocol

from proof_of_audit_agent.challenge_verifier import (
    CHALLENGE_CLAIM_SCHEMA_VERSION,
    EvidenceContext,
    StructuredChallengeClaim,
)
from proof_of_audit_agent.executable_evidence_runner import ExecutableEvidenceRunResult


_CONFIDENCE_ORDER = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


class ChallengeClaimExtractor(Protocol):
    def extract(
        self,
        *,
        context: EvidenceContext,
        run_result: ExecutableEvidenceRunResult,
    ) -> "ChallengeClaimExtractionResult":
        ...


@dataclass(frozen=True)
class ChallengeClaimExtractionResult:
    status: str
    claim: StructuredChallengeClaim | None = None
    detail: str | None = None
    model_metadata: dict[str, Any] = field(default_factory=dict)


class CommandBackedChallengeClaimExtractor:
    def __init__(
        self,
        *,
        command: str,
        provider: str | None = None,
        model: str | None = None,
        min_confidence: str = "medium",
        timeout_seconds: int = 30,
    ) -> None:
        self.command = command
        self.provider = provider
        self.model = model
        self.min_confidence = min_confidence.lower().strip() or "medium"
        self.timeout_seconds = timeout_seconds

    def extract(
        self,
        *,
        context: EvidenceContext,
        run_result: ExecutableEvidenceRunResult,
    ) -> ChallengeClaimExtractionResult:
        if not self.command.strip():
            return ChallengeClaimExtractionResult(
                status="extractor_unavailable",
                detail="Challenge claim extractor command is not configured.",
                model_metadata=self._base_model_metadata(status="extractor_unavailable"),
            )

        payload = self._build_payload(context=context, run_result=run_result)
        try:
            completed = subprocess.run(
                shlex.split(self.command),
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, ValueError) as exc:
            return ChallengeClaimExtractionResult(
                status="extractor_error",
                detail=str(exc),
                model_metadata=self._base_model_metadata(status="extractor_error"),
            )
        except subprocess.TimeoutExpired:
            return ChallengeClaimExtractionResult(
                status="extractor_error",
                detail=f"Challenge claim extraction exceeded {self.timeout_seconds}s.",
                model_metadata=self._base_model_metadata(status="extractor_error"),
            )

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or (
                f"Extractor exited with status {completed.returncode}."
            )
            return ChallengeClaimExtractionResult(
                status="extractor_error",
                detail=detail,
                model_metadata=self._base_model_metadata(
                    status="extractor_error",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                ),
            )

        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return ChallengeClaimExtractionResult(
                status="invalid_output",
                detail=f"Extractor did not return valid JSON: {exc}",
                model_metadata=self._base_model_metadata(
                    status="invalid_output",
                    raw_output=completed.stdout,
                ),
            )

        if not isinstance(response, dict):
            return ChallengeClaimExtractionResult(
                status="invalid_output",
                detail="Extractor must return a JSON object.",
                model_metadata=self._base_model_metadata(
                    status="invalid_output",
                    raw_output=completed.stdout,
                ),
            )

        raw_claim = response.get("claim")
        if not isinstance(raw_claim, dict):
            return ChallengeClaimExtractionResult(
                status="invalid_output",
                detail="Extractor JSON must contain a 'claim' object.",
                model_metadata=self._merge_model_metadata(
                    response,
                    status="invalid_output",
                    raw_output=completed.stdout,
                ),
            )

        claim, error = self._validate_claim(raw_claim)
        if error is not None:
            return ChallengeClaimExtractionResult(
                status="invalid_output",
                detail=error,
                model_metadata=self._merge_model_metadata(
                    response,
                    status="invalid_output",
                    raw_output=completed.stdout,
                ),
            )

        if self._confidence_rank(claim.confidence) < self._confidence_rank(
            self.min_confidence
        ):
            return ChallengeClaimExtractionResult(
                status="low_confidence",
                claim=claim,
                detail=(
                    f"Extractor confidence {claim.confidence!r} did not meet the "
                    f"configured minimum {self.min_confidence!r}."
                ),
                model_metadata=self._merge_model_metadata(
                    response,
                    status="low_confidence",
                    raw_output=completed.stdout,
                ),
            )

        return ChallengeClaimExtractionResult(
            status="complete",
            claim=claim,
            model_metadata=self._merge_model_metadata(
                response,
                status="complete",
                raw_output=completed.stdout,
            ),
        )

    def _build_payload(
        self,
        *,
        context: EvidenceContext,
        run_result: ExecutableEvidenceRunResult,
    ) -> dict[str, Any]:
        report = context.published_report if isinstance(context.published_report, dict) else {}
        normalized_findings = report.get("normalized_findings")
        if not isinstance(normalized_findings, list):
            normalized_findings = []
        return {
            "schema_version": CHALLENGE_CLAIM_SCHEMA_VERSION,
            "challenge": {
                "proof_uri": context.proof_uri,
                "evidence_type": context.evidence_type,
                "execution_env": context.execution_env,
                "evidence_manifest": context.evidence_manifest,
                "target_contract": context.target_contract,
                "benchmark_id": context.benchmark_id,
                "chain_id": context.chain_id,
            },
            "execution": {
                "summary": run_result.summary,
                "detail": run_result.detail,
                "stdout": run_result.stdout,
                "stderr": run_result.stderr,
                "backend": run_result.backend,
                "isolation_level": run_result.isolation_level,
                "source_path": run_result.source_path,
                "source_text": run_result.source_text,
                "fork_block_number": run_result.fork_block_number,
            },
            "audit": {
                "summary": report.get("summary"),
                "findings": report.get("findings"),
                "normalized_findings": normalized_findings,
            },
        }

    def _validate_claim(
        self, payload: dict[str, Any]
    ) -> tuple[StructuredChallengeClaim | None, str | None]:
        claim_type = payload.get("claim_type")
        basis = payload.get("basis")
        if not isinstance(claim_type, str) or not claim_type.strip():
            return None, "Extractor claim is missing a non-empty claim_type."
        if not isinstance(basis, str) or not basis.strip():
            return None, "Extractor claim is missing a non-empty basis."

        confidence = str(payload.get("confidence") or "unknown").lower().strip()
        if confidence not in _CONFIDENCE_ORDER:
            return None, f"Unsupported extractor confidence level: {confidence!r}"

        return (
            StructuredChallengeClaim(
                claim_type=claim_type.strip(),
                basis=basis.strip(),
                confidence=confidence,
                affected_surfaces=self._string_list(payload.get("affected_surfaces")),
                preconditions=self._string_list(payload.get("preconditions")),
                demonstrated_effect=self._optional_string(payload.get("demonstrated_effect")),
                claimed_impact=self._optional_string(payload.get("claimed_impact")),
                supporting_signals=self._string_list(payload.get("supporting_signals")),
            ),
            None,
        )

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str) and item.strip()]

    def _optional_string(self, value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value
        return None

    def _confidence_rank(self, confidence: str) -> int:
        return _CONFIDENCE_ORDER.get(confidence.lower().strip(), 0)

    def _base_model_metadata(
        self,
        *,
        status: str,
        raw_output: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "extractor": "command",
            "provider": self.provider,
            "model": self.model,
            "status": status,
        }
        if raw_output:
            payload["raw_output"] = raw_output
        if stdout:
            payload["stdout"] = stdout
        if stderr:
            payload["stderr"] = stderr
        return payload

    def _merge_model_metadata(
        self,
        response: dict[str, Any],
        *,
        status: str,
        raw_output: str | None = None,
    ) -> dict[str, Any]:
        model_metadata = response.get("model_metadata")
        payload = (
            dict(model_metadata)
            if isinstance(model_metadata, dict)
            else {}
        )
        payload.setdefault("extractor", "command")
        payload.setdefault("provider", self.provider)
        payload.setdefault("model", self.model)
        payload["status"] = status
        if raw_output is not None:
            payload.setdefault("raw_output", raw_output)
        return payload
