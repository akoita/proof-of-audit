"""Cross-agent claim watcher.

Polls the challenger feed to detect claims from *other* agents and reacts
according to the watching agent's configured ``challenge_strategy``:

- ``auto-challenge`` — automatically submit a challenge with evidence when
  the watcher's own analysis diverges from the published claim.
- ``flag-for-review`` — log the divergence for human review but do not
  submit a challenge automatically.
- ``silent-monitor`` — observe and log claims without further action.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

ChallengeStrategy = str  # "auto-challenge" | "flag-for-review" | "silent-monitor"


@dataclass(frozen=True)
class WatcherAgentConfig:
    """Configuration for the watching agent persona."""

    service_id: str
    name: str
    challenge_strategy: ChallengeStrategy = "silent-monitor"
    detectors: tuple[str, ...] = ()

    @classmethod
    def from_persona(cls, persona: dict[str, Any]) -> "WatcherAgentConfig":
        return cls(
            service_id=str(persona.get("service_id") or ""),
            name=str(persona.get("name") or ""),
            challenge_strategy=str(persona.get("challenge_strategy") or "silent-monitor"),
            detectors=tuple(
                str(d) for d in persona.get("detectors", [])
            ),
        )


@dataclass
class FindingDivergence:
    """Represents a vulnerability found by the watcher but missed by the claim."""

    finding_id: str
    title: str
    severity: str
    category: str
    description: str
    detector: str


@dataclass
class ClaimAnalysisResult:
    """Result of re-analyzing a contract that was the subject of a claim."""

    claim_event_id: str
    claim_audit_id: str
    claim_service_id: str
    target_contract: str
    watcher_service_id: str
    watcher_finding_count: int
    claim_finding_count: int
    divergences: list[FindingDivergence] = field(default_factory=list)
    action_taken: str = "none"  # "challenged" | "flagged" | "monitored" | "skipped"
    challenge_audit_id: str | None = None
    error: str | None = None

    @property
    def has_divergence(self) -> bool:
        return len(self.divergences) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_event_id": self.claim_event_id,
            "claim_audit_id": self.claim_audit_id,
            "claim_service_id": self.claim_service_id,
            "target_contract": self.target_contract,
            "watcher_service_id": self.watcher_service_id,
            "watcher_finding_count": self.watcher_finding_count,
            "claim_finding_count": self.claim_finding_count,
            "divergence_count": len(self.divergences),
            "divergences": [
                {
                    "finding_id": d.finding_id,
                    "title": d.title,
                    "severity": d.severity,
                    "category": d.category,
                    "detector": d.detector,
                }
                for d in self.divergences
            ],
            "action_taken": self.action_taken,
            "challenge_audit_id": self.challenge_audit_id,
            "error": self.error,
        }


@dataclass
class ClaimWatcher:
    """Watches the challenger feed and reacts to claims from other agents.

    The watcher polls ``GET /challenger-feed`` for newly published claims,
    filters out its own claims, re-analyzes the target contract, compares
    findings, and takes action based on the configured challenge strategy.
    """

    api_base_url: str
    agent_config: WatcherAgentConfig
    seen_event_ids: set[str] = field(default_factory=set)
    results: list[ClaimAnalysisResult] = field(default_factory=list)

    # -- Feed Polling --------------------------------------------------------

    def fetch_feed(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch the latest feed items from the challenger-feed endpoint."""
        query = urlencode({"limit": limit})
        url = f"{self.api_base_url.rstrip('/')}/challenger-feed?{query}"
        request = Request(url)
        request.add_header("Accept", "application/json")
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            items = payload.get("items", [])
            return items if isinstance(items, list) else []
        except Exception as exc:
            logger.warning("Failed to fetch challenger feed: %s", exc)
            return []

    def filter_new_claims(
        self, feed_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter feed items to only new ``audit_published`` events from other agents."""
        new_claims: list[dict[str, Any]] = []
        for item in feed_items:
            event_id = str(item.get("event_id") or "")
            event_kind = str(item.get("event_kind") or "")
            service_id = str(item.get("service_id") or "")

            if not event_id or event_id in self.seen_event_ids:
                continue

            self.seen_event_ids.add(event_id)

            # Only react to published claims from *other* agents
            if event_kind != "audit_published":
                continue
            if service_id == self.agent_config.service_id:
                continue

            new_claims.append(item)

        return new_claims

    # -- Re-Analysis ---------------------------------------------------------

    def reanalyze_contract(
        self, claim: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Submit the same contract for re-analysis by the watching agent.

        Returns the audit record from the API, or None on failure.
        """
        target_contract = str(claim.get("target_contract") or "")
        if not target_contract:
            return None

        submission = {
            "input_kind": "deployed_address",
            "contract_address": target_contract,
            "service_id": self.agent_config.service_id,
            "submitted_by": f"watcher:{self.agent_config.service_id}",
        }

        url = f"{self.api_base_url.rstrip('/')}/audits"
        request = Request(
            url,
            data=json.dumps(submission).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            logger.warning(
                "Failed to submit re-analysis for %s: %s", target_contract, exc
            )
            return None

    # -- Finding Comparison --------------------------------------------------

    def compare_findings(
        self,
        watcher_findings: list[dict[str, Any]],
        claim_finding_count: int,
    ) -> list[FindingDivergence]:
        """Identify findings from the watcher's analysis that may represent divergences.

        A divergence occurs when the watcher found vulnerabilities that the
        original claim's finding count suggests were missed. This is a
        heuristic: the watcher has more findings → likely missed vulnerabilities.
        """
        if not watcher_findings or len(watcher_findings) <= claim_finding_count:
            return []

        # Extra findings beyond what the original claim reported are divergences
        extra_findings = watcher_findings[claim_finding_count:]
        return [
            FindingDivergence(
                finding_id=str(f.get("finding_id") or ""),
                title=str(f.get("title") or ""),
                severity=str(f.get("severity") or "unknown"),
                category=str(f.get("category") or "unknown"),
                description=str(f.get("description") or ""),
                detector=str(f.get("detector") or "unknown"),
            )
            for f in extra_findings
        ]

    # -- Challenge Submission ------------------------------------------------

    def submit_challenge(
        self, audit_id: str, divergences: list[FindingDivergence]
    ) -> str | None:
        """Submit a challenge against the published claim.

        Returns the challenge tx hash on success, or None on failure.
        """
        evidence = {
            "schema_version": "cross-agent-challenge-evidence/v1",
            "challenger_service_id": self.agent_config.service_id,
            "challenger_name": self.agent_config.name,
            "timestamp": datetime.now(UTC).isoformat(),
            "divergences": [
                {
                    "finding_id": d.finding_id,
                    "title": d.title,
                    "severity": d.severity,
                    "category": d.category,
                    "detector": d.detector,
                    "description": d.description,
                }
                for d in divergences
            ],
        }
        proof_uri = f"data:application/json;base64,{_base64_encode(json.dumps(evidence))}"

        payload = {
            "proof_uri": proof_uri,
            "evidence_type": "deterministic_fixture",
            "challenger": self.agent_config.service_id,
        }

        url = f"{self.api_base_url.rstrip('/')}/audits/{audit_id}/challenge"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
                result = json.loads(response.read().decode("utf-8"))
            challenge = result.get("challenge", {})
            return str(challenge.get("challenge_tx_hash") or "")
        except Exception as exc:
            logger.warning("Failed to submit challenge for %s: %s", audit_id, exc)
            return None

    # -- Orchestration -------------------------------------------------------

    def process_claim(self, claim: dict[str, Any]) -> ClaimAnalysisResult:
        """Process a single published claim through the full watcher pipeline.

        1. Re-analyze the same contract
        2. Compare findings
        3. React according to challenge_strategy
        """
        event_id = str(claim.get("event_id") or "")
        audit_id = str(claim.get("audit_id") or "")
        service_id = str(claim.get("service_id") or "")
        target_contract = str(claim.get("target_contract") or "")
        claim_finding_count = int(claim.get("finding_count") or 0)

        logger.info(
            "[%s] Processing claim from %s on %s (findings=%d)",
            self.agent_config.service_id,
            service_id,
            target_contract,
            claim_finding_count,
        )

        # For silent-monitor, just observe
        if self.agent_config.challenge_strategy == "silent-monitor":
            result = ClaimAnalysisResult(
                claim_event_id=event_id,
                claim_audit_id=audit_id,
                claim_service_id=service_id,
                target_contract=target_contract,
                watcher_service_id=self.agent_config.service_id,
                watcher_finding_count=0,
                claim_finding_count=claim_finding_count,
                action_taken="monitored",
            )
            self.results.append(result)
            logger.info(
                "[%s] Silent monitor: observed claim %s",
                self.agent_config.service_id,
                event_id,
            )
            return result

        # Re-analyze the contract
        reanalysis = self.reanalyze_contract(claim)
        if reanalysis is None:
            result = ClaimAnalysisResult(
                claim_event_id=event_id,
                claim_audit_id=audit_id,
                claim_service_id=service_id,
                target_contract=target_contract,
                watcher_service_id=self.agent_config.service_id,
                watcher_finding_count=0,
                claim_finding_count=claim_finding_count,
                action_taken="skipped",
                error="re-analysis failed",
            )
            self.results.append(result)
            return result

        watcher_findings = reanalysis.get("report", {}).get("findings", [])
        divergences = self.compare_findings(watcher_findings, claim_finding_count)

        if not divergences:
            result = ClaimAnalysisResult(
                claim_event_id=event_id,
                claim_audit_id=audit_id,
                claim_service_id=service_id,
                target_contract=target_contract,
                watcher_service_id=self.agent_config.service_id,
                watcher_finding_count=len(watcher_findings),
                claim_finding_count=claim_finding_count,
                action_taken="monitored",
            )
            self.results.append(result)
            logger.info(
                "[%s] No divergence found for claim %s",
                self.agent_config.service_id,
                event_id,
            )
            return result

        # For flag-for-review, log but don't challenge
        if self.agent_config.challenge_strategy == "flag-for-review":
            result = ClaimAnalysisResult(
                claim_event_id=event_id,
                claim_audit_id=audit_id,
                claim_service_id=service_id,
                target_contract=target_contract,
                watcher_service_id=self.agent_config.service_id,
                watcher_finding_count=len(watcher_findings),
                claim_finding_count=claim_finding_count,
                divergences=divergences,
                action_taken="flagged",
            )
            self.results.append(result)
            logger.warning(
                "[%s] FLAGGED: %d divergences in claim %s from %s on %s",
                self.agent_config.service_id,
                len(divergences),
                event_id,
                service_id,
                target_contract,
            )
            return result

        # For auto-challenge, submit the challenge
        challenge_tx = self.submit_challenge(audit_id, divergences)
        result = ClaimAnalysisResult(
            claim_event_id=event_id,
            claim_audit_id=audit_id,
            claim_service_id=service_id,
            target_contract=target_contract,
            watcher_service_id=self.agent_config.service_id,
            watcher_finding_count=len(watcher_findings),
            claim_finding_count=claim_finding_count,
            divergences=divergences,
            action_taken="challenged" if challenge_tx else "skipped",
            challenge_audit_id=reanalysis.get("id"),
            error=None if challenge_tx else "challenge submission failed",
        )
        self.results.append(result)

        if challenge_tx:
            logger.info(
                "[%s] CHALLENGED: claim %s (tx=%s) — %d divergences",
                self.agent_config.service_id,
                event_id,
                challenge_tx,
                len(divergences),
            )
        else:
            logger.warning(
                "[%s] Challenge submission failed for claim %s",
                self.agent_config.service_id,
                event_id,
            )

        return result

    def poll_and_react(self, limit: int = 50) -> list[ClaimAnalysisResult]:
        """Single poll cycle: fetch → filter → process."""
        feed = self.fetch_feed(limit=limit)
        new_claims = self.filter_new_claims(feed)
        results: list[ClaimAnalysisResult] = []
        for claim in new_claims:
            result = self.process_claim(claim)
            results.append(result)
        return results


def _base64_encode(text: str) -> str:
    import base64

    return base64.b64encode(text.encode("utf-8")).decode("ascii")
