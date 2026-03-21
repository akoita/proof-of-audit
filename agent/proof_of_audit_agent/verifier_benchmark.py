from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from proof_of_audit_agent.challenge_claim_extractor import (
    ChallengeClaimExtractionResult,
)
from proof_of_audit_agent.challenge_verifier import (
    EvidenceContext,
    StructuredChallengeClaim,
)
from proof_of_audit_agent.executable_evidence_runner import ExecutableEvidenceRunResult
from proof_of_audit_agent.executable_evidence_verifier import ExecutableEvidenceVerifier


BENCHMARK_SCHEMA_VERSION = "challenge-verifier-benchmark/v1"
DEFAULT_BENCHMARK_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "challenge_verifier_v2_cases.json"
)
CLASSIFICATION_LABELS = (
    "already_covered",
    "likely_new_issue",
    "contradicts_audit_claim",
    "same_root_cause_variant",
    "ambiguous",
)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    description: str
    context: EvidenceContext
    run_result: ExecutableEvidenceRunResult
    extractor_result: ChallengeClaimExtractionResult | None
    expected: dict[str, Any]


class ReplayableRunner:
    def __init__(self, result: ExecutableEvidenceRunResult) -> None:
        self.result = result

    def run(self, context: EvidenceContext) -> ExecutableEvidenceRunResult:
        del context
        return self.result


class ReplayableExtractor:
    def __init__(self, result: ChallengeClaimExtractionResult) -> None:
        self.result = result

    def extract(
        self,
        *,
        context: EvidenceContext,
        run_result: ExecutableEvidenceRunResult,
    ) -> ChallengeClaimExtractionResult:
        del context, run_result
        return self.result


def _structured_claim_from_payload(payload: Any) -> StructuredChallengeClaim | None:
    if not isinstance(payload, dict):
        return None
    return StructuredChallengeClaim(
        claim_type=str(payload.get("claim_type") or "generic_claim"),
        basis=str(payload.get("basis") or "unknown"),
        confidence=str(payload.get("confidence") or "unknown"),
        affected_surfaces=[
            str(item)
            for item in payload.get("affected_surfaces", [])
            if isinstance(item, str) and item
        ],
        preconditions=[
            str(item)
            for item in payload.get("preconditions", [])
            if isinstance(item, str) and item
        ],
        demonstrated_effect=(
            str(payload.get("demonstrated_effect"))
            if payload.get("demonstrated_effect") is not None
            else None
        ),
        claimed_impact=(
            str(payload.get("claimed_impact"))
            if payload.get("claimed_impact") is not None
            else None
        ),
        supporting_signals=[
            str(item)
            for item in payload.get("supporting_signals", [])
            if isinstance(item, str) and item
        ],
        schema_version=str(payload.get("schema_version") or "challenge-claim/v1"),
    )


def _extractor_result_from_payload(payload: Any) -> ChallengeClaimExtractionResult | None:
    if not isinstance(payload, dict):
        return None
    return ChallengeClaimExtractionResult(
        status=str(payload.get("status") or "extractor_unavailable"),
        claim=_structured_claim_from_payload(payload.get("claim")),
        detail=(
            str(payload.get("detail"))
            if payload.get("detail") is not None
            else None
        ),
        model_metadata=(
            dict(payload.get("model_metadata"))
            if isinstance(payload.get("model_metadata"), dict)
            else {}
        ),
    )


def load_benchmark_cases(path: Path | None = None) -> list[BenchmarkCase]:
    corpus_path = path or DEFAULT_BENCHMARK_CORPUS
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise ValueError("Unsupported benchmark corpus schema version.")

    cases: list[BenchmarkCase] = []
    for raw_case in payload.get("cases", []):
        if not isinstance(raw_case, dict):
            continue
        context_payload = raw_case.get("context")
        run_payload = raw_case.get("run_result")
        if not isinstance(context_payload, dict) or not isinstance(run_payload, dict):
            continue
        cases.append(
            BenchmarkCase(
                case_id=str(raw_case.get("case_id") or "unknown-case"),
                category=str(raw_case.get("category") or "uncategorized"),
                description=str(raw_case.get("description") or ""),
                context=EvidenceContext(
                    proof_uri=str(context_payload.get("proof_uri") or ""),
                    benchmark_id=(
                        str(context_payload.get("benchmark_id"))
                        if context_payload.get("benchmark_id") is not None
                        else None
                    ),
                    target_contract=str(context_payload.get("target_contract") or ""),
                    published_report=(
                        dict(context_payload.get("published_report"))
                        if isinstance(context_payload.get("published_report"), dict)
                        else {}
                    ),
                    evidence_type=str(
                        context_payload.get("evidence_type") or "executable_test"
                    ),
                    execution_env=(
                        str(context_payload.get("execution_env"))
                        if context_payload.get("execution_env") is not None
                        else None
                    ),
                    evidence_manifest=(
                        dict(context_payload.get("evidence_manifest"))
                        if isinstance(context_payload.get("evidence_manifest"), dict)
                        else None
                    ),
                    chain_id=(
                        int(context_payload.get("chain_id"))
                        if context_payload.get("chain_id") is not None
                        else None
                    ),
                    rpc_url=(
                        str(context_payload.get("rpc_url"))
                        if context_payload.get("rpc_url") is not None
                        else None
                    ),
                    committed_evidence_hash=(
                        str(context_payload.get("committed_evidence_hash"))
                        if context_payload.get("committed_evidence_hash") is not None
                        else None
                    ),
                ),
                run_result=ExecutableEvidenceRunResult(
                    outcome=str(run_payload.get("outcome") or "runner_error"),
                    summary=str(run_payload.get("summary") or ""),
                    detail=str(run_payload.get("detail") or ""),
                    stdout=str(run_payload.get("stdout") or ""),
                    stderr=str(run_payload.get("stderr") or ""),
                    backend=(
                        str(run_payload.get("backend"))
                        if run_payload.get("backend") is not None
                        else None
                    ),
                    isolation_level=(
                        str(run_payload.get("isolation_level"))
                        if run_payload.get("isolation_level") is not None
                        else None
                    ),
                    source_path=(
                        str(run_payload.get("source_path"))
                        if run_payload.get("source_path") is not None
                        else None
                    ),
                    source_text=(
                        str(run_payload.get("source_text"))
                        if run_payload.get("source_text") is not None
                        else None
                    ),
                    fork_block_number=(
                        int(run_payload.get("fork_block_number"))
                        if run_payload.get("fork_block_number") is not None
                        else None
                    ),
                ),
                extractor_result=_extractor_result_from_payload(
                    raw_case.get("extractor_result")
                ),
                expected=(
                    dict(raw_case.get("expected"))
                    if isinstance(raw_case.get("expected"), dict)
                    else {}
                ),
            )
        )
    return cases


def _case_result_payload(case: BenchmarkCase) -> dict[str, Any]:
    extractor = (
        ReplayableExtractor(case.extractor_result)
        if case.extractor_result is not None
        else None
    )
    verifier = ExecutableEvidenceVerifier(
        runner=ReplayableRunner(case.run_result),
        extractor=extractor,
    )
    result = verifier.verify(case.context)
    dossier = result.verification_dossier
    actual = {
        "verification_status": result.status,
        "comparison_status": (
            dossier.comparison_status if dossier is not None else "unknown"
        ),
        "policy_status": dossier.policy_status if dossier is not None else "unknown",
        "recommended_resolution": (
            dossier.recommended_resolution if dossier is not None else result.resolution
        ),
        "resolution": result.resolution,
        "verifier": result.verifier,
        "advisory_only": result.advisory_only,
    }
    mismatches = [
        field
        for field, expected_value in case.expected.items()
        if actual.get(field) != expected_value
    ]

    claim_payload = result.challenge_claim.to_payload() if result.challenge_claim else None
    dossier_payload = dossier.to_payload() if dossier is not None else None
    model_metadata = {}
    if dossier_payload is not None and isinstance(dossier_payload.get("model_metadata"), dict):
        model_metadata = dict(dossier_payload["model_metadata"])

    return {
        "case_id": case.case_id,
        "category": case.category,
        "description": case.description,
        "expected": case.expected,
        "actual": actual,
        "pass": not mismatches,
        "mismatches": mismatches,
        "claim": claim_payload,
        "dossier": dossier_payload,
        "version_metadata": {
            "verifier_version": (
                dossier_payload.get("verifier_version")
                if isinstance(dossier_payload, dict)
                else result.verifier
            ),
            "claim_schema_version": (
                claim_payload.get("schema_version")
                if isinstance(claim_payload, dict)
                else None
            ),
            "dossier_schema_version": (
                dossier_payload.get("schema_version")
                if isinstance(dossier_payload, dict)
                else None
            ),
            "normalized_finding_schema_versions": sorted(
                {
                    str(finding.get("schema_version"))
                    for finding in case.context.published_report.get(
                        "normalized_findings", []
                    )
                    if isinstance(finding, dict) and finding.get("schema_version")
                }
            ),
            "model_metadata": model_metadata,
        },
    }


def _classification_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [
        item
        for item in results
        if item["expected"].get("comparison_status") in CLASSIFICATION_LABELS
    ]
    total = len(evaluated)
    correct = sum(
        1
        for item in evaluated
        if item["actual"].get("comparison_status")
        == item["expected"].get("comparison_status")
    )
    per_label: dict[str, Any] = {}
    confusion: dict[str, dict[str, int]] = {}
    for label in CLASSIFICATION_LABELS:
        tp = fp = fn = 0
        confusion[label] = {}
        for item in evaluated:
            expected = str(item["expected"].get("comparison_status"))
            actual = str(item["actual"].get("comparison_status"))
            if expected == label and actual == label:
                tp += 1
            elif expected != label and actual == label:
                fp += 1
            elif expected == label and actual != label:
                fn += 1
            if expected == label:
                confusion[label][actual] = confusion[label].get(actual, 0) + 1
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (
            (2 * precision * recall) / (precision + recall)
            if precision not in {None, 0} and recall not in {None, 0}
            else None
        )
        per_label[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(
                1
                for item in evaluated
                if item["expected"].get("comparison_status") == label
            ),
        }
    return {
        "evaluated_cases": total,
        "correct": correct,
        "accuracy": (correct / total) if total else None,
        "per_label": per_label,
        "confusion_by_expected_label": confusion,
    }


def run_benchmark(path: Path | None = None) -> dict[str, Any]:
    corpus_path = path or DEFAULT_BENCHMARK_CORPUS
    cases = load_benchmark_cases(corpus_path)
    results = [_case_result_payload(case) for case in cases]
    passed = sum(1 for item in results if item["pass"])
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "corpus_path": str(corpus_path),
        "summary": {
            "total_cases": len(results),
            "passed_cases": passed,
            "failed_cases": len(results) - passed,
            "pass_rate": (passed / len(results)) if results else None,
            "categories": {
                category: sum(1 for item in results if item["category"] == category)
                for category in sorted({item["category"] for item in results})
            },
        },
        "metrics": _classification_metrics(results),
        "cases": results,
    }

