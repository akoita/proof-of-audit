from __future__ import annotations

from dataclasses import dataclass, field
import re

from proof_of_audit_agent.challenge_verifier import (
    StructuredChallengeClaim,
    VerificationFindingMatch,
)


_CONFIDENCE_RANK = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
_REPORT_CLEAN_CUES = {
    "clean",
    "clean report",
    "no findings",
    "no issues",
    "no material issues",
    "no vulnerabilities",
    "safe",
}
_CLASS_ALIASES = {
    "access_control": {
        "access_control",
        "access",
        "authorization",
        "auth",
        "owner",
        "admin",
        "unauthorized",
        "privileged",
    },
    "reentrancy": {"reentrancy", "reentrant"},
    "unchecked_external_call": {
        "unchecked_external_call",
        "unchecked",
        "external-call",
        "externalcall",
        "call",
        "lowlevelcall",
    },
}


def _normalize_text(value: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    tokens = {token for token in normalized.split() if len(token) >= 3}
    compact = normalized.replace(" ", "")
    if compact:
        tokens.add(compact)
    return tokens


def _confidence_at_least(value: str, minimum: str) -> bool:
    return _CONFIDENCE_RANK.get(value, 0) >= _CONFIDENCE_RANK.get(minimum, 0)


@dataclass(frozen=True)
class SemanticComparisonResult:
    outcome: str
    confidence: str
    rationale: str
    matched_finding_ids: list[str] = field(default_factory=list)
    matched_findings: list[VerificationFindingMatch] = field(default_factory=list)
    unmatched_signals: list[str] = field(default_factory=list)
    disagreement_status: str = "not_checked"
    disagreement_detail: str | None = None


@dataclass(frozen=True)
class SemanticPolicyDecision:
    status: str
    recommended_resolution: str
    abstained: bool
    confidence: str
    rationale: str


class SemanticChallengeComparator:
    def compare(
        self,
        *,
        claim: StructuredChallengeClaim | None,
        published_report: dict[str, object],
    ) -> SemanticComparisonResult:
        if claim is None:
            return SemanticComparisonResult(
                outcome="ambiguous",
                confidence="low",
                rationale="No structured challenge claim was available for semantic comparison.",
            )

        normalized_findings = published_report.get("normalized_findings")
        if not isinstance(normalized_findings, list):
            normalized_findings = []
        if not normalized_findings:
            normalized_findings = self._build_fallback_normalized_findings(published_report)

        claim_classes = self._claim_classes(claim)
        claim_surfaces = {
            surface.lower() for surface in claim.affected_surfaces if surface.strip()
        }
        claim_preconditions = {
            item.lower() for item in claim.preconditions if item.strip()
        }
        claim_signals = self._claim_signal_tokens(claim)
        focus_signals = self._claim_focus_tokens(claim)

        direct_matches: list[VerificationFindingMatch] = []
        variant_matches: list[VerificationFindingMatch] = []
        remaining_signals = set(claim_signals)
        top_score = 0.0

        for raw_finding in normalized_findings:
            if not isinstance(raw_finding, dict):
                continue
            finding_id = str(raw_finding.get("finding_id") or "finding")
            finding_classes = {
                str(item).lower()
                for item in raw_finding.get("vulnerability_classes", [])
                if isinstance(item, str) and item
            }
            finding_surfaces = {
                str(item).lower()
                for item in raw_finding.get("affected_surfaces", [])
                if isinstance(item, str) and item
            }
            finding_preconditions = {
                str(item).lower()
                for item in raw_finding.get("preconditions", [])
                if isinstance(item, str) and item
            }
            finding_keywords = {
                str(item).lower()
                for item in raw_finding.get("keywords", [])
                if isinstance(item, str) and item
            }
            class_overlap = claim_classes & finding_classes
            surface_overlap = claim_surfaces & finding_surfaces
            precondition_overlap = claim_preconditions & finding_preconditions
            keyword_overlap = claim_signals & finding_keywords
            focus_overlap = focus_signals & finding_keywords
            score = (
                (4.0 if class_overlap else 0.0)
                + (3.0 if surface_overlap else 0.0)
                + (2.0 if precondition_overlap else 0.0)
                + min(2.0, float(len(keyword_overlap)) * 0.5)
            )
            top_score = max(top_score, score)
            if not class_overlap and score < 2.5:
                continue

            relationship = "same_root_cause_variant"
            confidence = "low"
            rationale_parts: list[str] = []
            if class_overlap:
                rationale_parts.append(
                    "shares vulnerability class "
                    + ", ".join(sorted(class_overlap))
                )
            if surface_overlap:
                rationale_parts.append(
                    "touches surface " + ", ".join(sorted(surface_overlap))
                )
            if precondition_overlap:
                rationale_parts.append(
                    "shares preconditions " + ", ".join(sorted(precondition_overlap))
                )
            if keyword_overlap:
                rationale_parts.append(
                    "overlaps evidence keywords "
                    + ", ".join(sorted(keyword_overlap)[:4])
                )

            if surface_overlap and "reported" in claim_signals:
                relationship = "already_covered"
                confidence = "medium"
            elif class_overlap and (surface_overlap or len(focus_overlap) >= 2):
                relationship = "already_covered"
                confidence = "high" if score >= 7.0 else "medium"
            elif class_overlap or (surface_overlap and keyword_overlap):
                relationship = "same_root_cause_variant"
                confidence = "medium" if score >= 4.0 else "low"

            match = VerificationFindingMatch(
                finding_id=finding_id,
                relationship=relationship,
                confidence=confidence,
                rationale="; ".join(rationale_parts) or "Partial semantic overlap.",
                score=score,
            )
            if relationship == "already_covered":
                direct_matches.append(match)
                remaining_signals.difference_update(finding_keywords)
                remaining_signals.difference_update(finding_surfaces)
            else:
                variant_matches.append(match)

        if direct_matches:
            best = sorted(direct_matches, key=lambda item: item.score or 0.0, reverse=True)
            return SemanticComparisonResult(
                outcome="already_covered",
                confidence=best[0].confidence,
                rationale=(
                    "The reproduced exploit aligns with published finding(s): "
                    + ", ".join(match.finding_id for match in best)
                    + "."
                ),
                matched_finding_ids=[match.finding_id for match in best],
                matched_findings=best,
                unmatched_signals=sorted(remaining_signals),
                disagreement_status="no_disagreement",
            )

        contradiction = self._contradicts_published_claim(claim=claim, published_report=published_report)
        if contradiction is not None:
            return SemanticComparisonResult(
                outcome="contradicts_audit_claim",
                confidence="high" if claim.confidence == "high" else "medium",
                rationale=contradiction,
                unmatched_signals=sorted(remaining_signals),
                disagreement_status="no_disagreement",
            )

        if variant_matches:
            best = sorted(variant_matches, key=lambda item: item.score or 0.0, reverse=True)
            return SemanticComparisonResult(
                outcome="same_root_cause_variant",
                confidence=best[0].confidence,
                rationale=(
                    "The reproduced exploit partially overlaps published finding(s) but not strongly enough to classify it as already covered."
                ),
                matched_finding_ids=[match.finding_id for match in best],
                matched_findings=best,
                unmatched_signals=sorted(remaining_signals),
                disagreement_status="no_disagreement",
            )

        if claim.confidence in {"unknown", "low"} or claim.claim_type == "generic_executable_claim":
            return SemanticComparisonResult(
                outcome="ambiguous",
                confidence="low" if claim.confidence != "high" else "medium",
                rationale=(
                    "The reproduced exploit could not be mapped to a published finding with enough semantic confidence."
                ),
                unmatched_signals=sorted(remaining_signals),
                disagreement_status="no_disagreement",
            )

        return SemanticComparisonResult(
            outcome="likely_new_issue",
            confidence="medium" if claim.confidence != "high" else "high",
            rationale=(
                "The reproduced exploit does not semantically align with the normalized published findings and appears to represent a new issue."
            ),
            unmatched_signals=sorted(remaining_signals),
            disagreement_status="no_disagreement",
        )

    def _claim_classes(self, claim: StructuredChallengeClaim) -> set[str]:
        values = {claim.claim_type.lower()}
        values.update(_CLASS_ALIASES.get(claim.claim_type.lower(), set()))
        for signal in claim.supporting_signals:
            lowered = signal.lower()
            for canonical, aliases in _CLASS_ALIASES.items():
                if lowered in aliases:
                    values.add(canonical)
                    values.update(aliases)
        return values

    def _claim_signal_tokens(self, claim: StructuredChallengeClaim) -> set[str]:
        values: set[str] = set()
        for item in (
            [claim.claim_type, claim.basis]
            + claim.affected_surfaces
            + claim.preconditions
            + claim.supporting_signals
            + ([claim.demonstrated_effect] if claim.demonstrated_effect else [])
            + ([claim.claimed_impact] if claim.claimed_impact else [])
        ):
            if isinstance(item, str) and item:
                values.update(_normalize_text(item))
        return values

    def _claim_focus_tokens(self, claim: StructuredChallengeClaim) -> set[str]:
        values: set[str] = set()
        for item in [claim.claim_type] + claim.affected_surfaces + claim.supporting_signals:
            if isinstance(item, str) and item:
                values.update(_normalize_text(item))
        return values

    def _contradicts_published_claim(
        self,
        *,
        claim: StructuredChallengeClaim,
        published_report: dict[str, object],
    ) -> str | None:
        findings = published_report.get("findings")
        finding_count = len(findings) if isinstance(findings, list) else 0
        summary = str(published_report.get("summary") or "").lower()
        normalized_summary = " ".join(summary.split())
        if finding_count == 0 and any(cue in normalized_summary for cue in _REPORT_CLEAN_CUES):
            return (
                "The published audit summary presents the target as clean or issue-free, but the reproduced exploit demonstrates a concrete issue."
            )
        if "no critical" in normalized_summary and claim.claimed_impact:
            impact_tokens = _normalize_text(claim.claimed_impact)
            if {"takeover", "drain", "loss", "privilege"} & impact_tokens:
                return (
                    "The reproduced exploit indicates a material impact that conflicts with the published audit summary."
                )
        return None

    def _build_fallback_normalized_findings(
        self, published_report: dict[str, object]
    ) -> list[dict[str, object]]:
        findings = published_report.get("findings")
        if not isinstance(findings, list):
            return []

        normalized: list[dict[str, object]] = []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            affected_function = str(finding.get("affected_function") or "").strip()
            affected_surface = affected_function.split("(", 1)[0] if affected_function else ""
            category = str(finding.get("category") or "general").lower()
            detector = str(finding.get("detector") or "deterministic.legacy").lower()
            keywords = set()
            for key in ("title", "description", "category", "detector", "affected_function"):
                value = finding.get(key)
                if isinstance(value, str) and value.strip():
                    keywords.update(_normalize_text(value))
            normalized.append(
                {
                    "finding_id": str(finding.get("finding_id") or finding.get("title") or "finding"),
                    "vulnerability_classes": [category, detector.split(".")[-1]],
                    "affected_surfaces": [affected_surface] if affected_surface else [],
                    "preconditions": [],
                    "keywords": sorted(keywords),
                }
            )
        return normalized


class AbstentionFirstPolicy:
    def __init__(self, *, minimum_confidence: str = "medium") -> None:
        self.minimum_confidence = minimum_confidence

    def decide(self, comparison: SemanticComparisonResult) -> SemanticPolicyDecision:
        if comparison.disagreement_status not in {"not_checked", "no_disagreement"}:
            return SemanticPolicyDecision(
                status="manual_review_required",
                recommended_resolution="manual_review_required",
                abstained=True,
                confidence="low",
                rationale=(
                    comparison.disagreement_detail
                    or "Semantic comparison passes disagreed, so the verifier abstains."
                ),
            )
        if not _confidence_at_least(comparison.confidence, self.minimum_confidence):
            return SemanticPolicyDecision(
                status="manual_review_required",
                recommended_resolution="manual_review_required",
                abstained=True,
                confidence=comparison.confidence,
                rationale=(
                    "Semantic comparison confidence is below the abstention threshold."
                ),
            )
        if comparison.outcome == "already_covered":
            return SemanticPolicyDecision(
                status="rejected",
                recommended_resolution="rejected",
                abstained=False,
                confidence=comparison.confidence,
                rationale=comparison.rationale,
            )
        if comparison.outcome in {"likely_new_issue", "contradicts_audit_claim"}:
            return SemanticPolicyDecision(
                status="manual_review_required",
                recommended_resolution="upheld",
                abstained=True,
                confidence=comparison.confidence,
                rationale=comparison.rationale,
            )
        return SemanticPolicyDecision(
            status="manual_review_required",
            recommended_resolution="manual_review_required",
            abstained=True,
            confidence=comparison.confidence,
            rationale=comparison.rationale,
        )
