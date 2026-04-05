"""Tests for cross-agent claim watcher (issue #276).

Validates:
- Feed polling and event filtering
- Finding comparison and divergence detection
- Challenge strategy routing (auto-challenge, flag-for-review, silent-monitor)
- WatcherAgentConfig construction from persona manifests
- ClaimAnalysisResult serialization
"""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from proof_of_audit_agent.claim_watcher import (
    ClaimAnalysisResult,
    ClaimWatcher,
    FindingDivergence,
    WatcherAgentConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_feed_item(
    event_id: str = "audit-1::published",
    event_kind: str = "audit_published",
    service_id: str = "agent-other",
    audit_id: str = "audit-1",
    target_contract: str = "0xabc",
    finding_count: int = 2,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_kind": event_kind,
        "service_id": service_id,
        "audit_id": audit_id,
        "target_contract": target_contract,
        "finding_count": finding_count,
        "current_state": "published",
        "summary": "test claim",
    }


def _build_findings(count: int) -> list[dict[str, Any]]:
    return [
        {
            "finding_id": f"FIND-{i}",
            "title": f"Finding {i}",
            "severity": "high" if i % 2 == 0 else "medium",
            "category": "reentrancy",
            "description": f"Test finding {i}",
            "detector": "reentrancy",
        }
        for i in range(count)
    ]


@pytest.fixture()
def hawk_config() -> WatcherAgentConfig:
    return WatcherAgentConfig(
        service_id="agent-reentrancy-hawk",
        name="Reentrancy Hawk",
        challenge_strategy="auto-challenge",
        detectors=("reentrancy",),
    )


@pytest.fixture()
def monitor_config() -> WatcherAgentConfig:
    return WatcherAgentConfig(
        service_id="agent-monitor",
        name="Silent Monitor",
        challenge_strategy="silent-monitor",
    )


@pytest.fixture()
def reviewer_config() -> WatcherAgentConfig:
    return WatcherAgentConfig(
        service_id="agent-reviewer",
        name="Flag Reviewer",
        challenge_strategy="flag-for-review",
        detectors=("reentrancy", "access_control"),
    )


# ---------------------------------------------------------------------------
# Tests: WatcherAgentConfig
# ---------------------------------------------------------------------------


class TestWatcherAgentConfig:
    def test_from_persona(self):
        persona = {
            "service_id": "agent-hawk",
            "name": "Hawk",
            "challenge_strategy": "auto-challenge",
            "detectors": ["reentrancy", "access_control"],
        }
        cfg = WatcherAgentConfig.from_persona(persona)
        assert cfg.service_id == "agent-hawk"
        assert cfg.name == "Hawk"
        assert cfg.challenge_strategy == "auto-challenge"
        assert cfg.detectors == ("reentrancy", "access_control")

    def test_from_persona_defaults(self):
        cfg = WatcherAgentConfig.from_persona({})
        assert cfg.service_id == ""
        assert cfg.challenge_strategy == "silent-monitor"
        assert cfg.detectors == ()

    def test_from_persona_missing_strategy(self):
        persona = {"service_id": "test", "name": "Test"}
        cfg = WatcherAgentConfig.from_persona(persona)
        assert cfg.challenge_strategy == "silent-monitor"


# ---------------------------------------------------------------------------
# Tests: Feed Filtering
# ---------------------------------------------------------------------------


class TestFeedFiltering:
    def test_filters_own_claims(self, hawk_config: WatcherAgentConfig):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        feed = [
            _build_feed_item(service_id="agent-reentrancy-hawk"),  # own claim
            _build_feed_item(
                event_id="audit-2::published",
                service_id="agent-other",
            ),
        ]
        new = watcher.filter_new_claims(feed)
        assert len(new) == 1
        assert new[0]["service_id"] == "agent-other"

    def test_filters_non_published_events(self, hawk_config: WatcherAgentConfig):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        feed = [
            _build_feed_item(event_kind="challenge_opened"),
            _build_feed_item(event_kind="challenge_resolved"),
        ]
        new = watcher.filter_new_claims(feed)
        assert len(new) == 0

    def test_deduplicates_seen_events(self, hawk_config: WatcherAgentConfig):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        feed = [_build_feed_item(event_id="same-event")]
        assert len(watcher.filter_new_claims(feed)) == 1
        assert len(watcher.filter_new_claims(feed)) == 0  # seen already

    def test_accepts_new_claims_from_other_agents(
        self, hawk_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        feed = [
            _build_feed_item(event_id="a1::published", service_id="agent-sentinel"),
            _build_feed_item(event_id="a2::published", service_id="agent-guardian"),
        ]
        new = watcher.filter_new_claims(feed)
        assert len(new) == 2


# ---------------------------------------------------------------------------
# Tests: Finding Comparison
# ---------------------------------------------------------------------------


class TestFindingComparison:
    def test_no_divergence_when_same_count(self, hawk_config: WatcherAgentConfig):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        findings = _build_findings(3)
        divergences = watcher.compare_findings(findings, claim_finding_count=3)
        assert len(divergences) == 0

    def test_no_divergence_when_fewer_findings(
        self, hawk_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        findings = _build_findings(2)
        divergences = watcher.compare_findings(findings, claim_finding_count=5)
        assert len(divergences) == 0

    def test_divergence_when_more_findings(self, hawk_config: WatcherAgentConfig):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        findings = _build_findings(5)
        divergences = watcher.compare_findings(findings, claim_finding_count=2)
        assert len(divergences) == 3

    def test_divergence_details(self, hawk_config: WatcherAgentConfig):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        findings = _build_findings(3)
        divergences = watcher.compare_findings(findings, claim_finding_count=1)
        assert len(divergences) == 2
        assert all(isinstance(d, FindingDivergence) for d in divergences)
        assert divergences[0].finding_id == "FIND-1"
        assert divergences[1].finding_id == "FIND-2"

    def test_no_divergence_with_empty_findings(
        self, hawk_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        divergences = watcher.compare_findings([], claim_finding_count=3)
        assert len(divergences) == 0


# ---------------------------------------------------------------------------
# Tests: Strategy Routing
# ---------------------------------------------------------------------------


class TestStrategyRouting:
    def test_silent_monitor_skips_reanalysis(
        self, monitor_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=monitor_config,
        )
        claim = _build_feed_item()
        with patch.object(watcher, "reanalyze_contract") as mock_reanalyze:
            result = watcher.process_claim(claim)
            mock_reanalyze.assert_not_called()

        assert result.action_taken == "monitored"
        assert result.watcher_finding_count == 0

    def test_flag_for_review_does_not_challenge(
        self, reviewer_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=reviewer_config,
        )
        claim = _build_feed_item(finding_count=1)
        mock_audit = {
            "id": "watcher-audit-1",
            "report": {"findings": _build_findings(4)},
        }
        with patch.object(watcher, "reanalyze_contract", return_value=mock_audit):
            with patch.object(watcher, "submit_challenge") as mock_challenge:
                result = watcher.process_claim(claim)
                mock_challenge.assert_not_called()

        assert result.action_taken == "flagged"
        assert result.has_divergence
        assert len(result.divergences) == 3

    def test_auto_challenge_submits_when_divergent(
        self, hawk_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        claim = _build_feed_item(finding_count=1)
        mock_audit = {
            "id": "watcher-audit-1",
            "report": {"findings": _build_findings(3)},
        }
        with patch.object(watcher, "reanalyze_contract", return_value=mock_audit):
            with patch.object(
                watcher, "submit_challenge", return_value="0xdeadbeef"
            ) as mock_challenge:
                result = watcher.process_claim(claim)
                mock_challenge.assert_called_once()

        assert result.action_taken == "challenged"
        assert len(result.divergences) == 2

    def test_auto_challenge_no_divergence_results_in_monitored(
        self, hawk_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        claim = _build_feed_item(finding_count=5)
        mock_audit = {
            "id": "watcher-audit-1",
            "report": {"findings": _build_findings(3)},  # fewer than claim
        }
        with patch.object(watcher, "reanalyze_contract", return_value=mock_audit):
            result = watcher.process_claim(claim)

        assert result.action_taken == "monitored"
        assert not result.has_divergence

    def test_reanalysis_failure_results_in_skipped(
        self, hawk_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        claim = _build_feed_item()
        with patch.object(watcher, "reanalyze_contract", return_value=None):
            result = watcher.process_claim(claim)

        assert result.action_taken == "skipped"
        assert result.error == "re-analysis failed"


# ---------------------------------------------------------------------------
# Tests: ClaimAnalysisResult
# ---------------------------------------------------------------------------


class TestClaimAnalysisResult:
    def test_to_dict(self):
        result = ClaimAnalysisResult(
            claim_event_id="e1",
            claim_audit_id="a1",
            claim_service_id="agent-other",
            target_contract="0xabc",
            watcher_service_id="agent-hawk",
            watcher_finding_count=5,
            claim_finding_count=2,
            divergences=[
                FindingDivergence(
                    finding_id="F1",
                    title="Reentrancy",
                    severity="high",
                    category="reentrancy",
                    description="test",
                    detector="reentrancy",
                )
            ],
            action_taken="challenged",
        )
        d = result.to_dict()
        assert d["divergence_count"] == 1
        assert d["action_taken"] == "challenged"
        assert d["divergences"][0]["finding_id"] == "F1"

    def test_has_divergence(self):
        result = ClaimAnalysisResult(
            claim_event_id="e1",
            claim_audit_id="a1",
            claim_service_id="s1",
            target_contract="0x1",
            watcher_service_id="s2",
            watcher_finding_count=0,
            claim_finding_count=0,
        )
        assert not result.has_divergence

        result.divergences.append(
            FindingDivergence("F1", "T", "H", "C", "D", "R")
        )
        assert result.has_divergence


# ---------------------------------------------------------------------------
# Tests: Poll and React Integration
# ---------------------------------------------------------------------------


class TestPollAndReact:
    def test_full_poll_cycle(self, hawk_config: WatcherAgentConfig):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        feed = [
            _build_feed_item(
                event_id="a1::published",
                service_id="agent-sentinel",
                finding_count=1,
            ),
        ]
        mock_audit = {
            "id": "reanalysis-1",
            "report": {"findings": _build_findings(4)},
        }
        with patch.object(watcher, "fetch_feed", return_value=feed):
            with patch.object(
                watcher, "reanalyze_contract", return_value=mock_audit
            ):
                with patch.object(
                    watcher, "submit_challenge", return_value="0xabc"
                ):
                    results = watcher.poll_and_react()

        assert len(results) == 1
        assert results[0].action_taken == "challenged"
        assert len(results[0].divergences) == 3
        assert len(watcher.results) == 1

    def test_poll_cycle_with_no_new_claims(
        self, hawk_config: WatcherAgentConfig
    ):
        watcher = ClaimWatcher(
            api_base_url="http://localhost:9999",
            agent_config=hawk_config,
        )
        with patch.object(watcher, "fetch_feed", return_value=[]):
            results = watcher.poll_and_react()
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Tests: CLI Script (cross_agent_watcher.py)
# ---------------------------------------------------------------------------


class TestCLIScript:
    def test_resolve_agent_config_from_manifest(self, tmp_path: Path):
        manifest = {
            "schema_version": "agent-personas/v1",
            "agents": [
                {
                    "service_id": "agent-hawk",
                    "name": "Hawk",
                    "challenge_strategy": "auto-challenge",
                    "detectors": ["reentrancy"],
                    "profile": "hawk",
                    "runtime_mode": "hybrid",
                    "capabilities": ["audit_contract"],
                    "identity": {"agent_id": 1, "operator": "T", "anvil_account_index": 1},
                },
            ],
        }
        manifest_path = tmp_path / "agents.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        sys_path_backup = list(__import__("sys").path)
        try:
            __import__("sys").path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
            # Import resolve functions
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "cross_agent_watcher",
                str(Path(__file__).resolve().parent.parent.parent / "scripts" / "cross_agent_watcher.py"),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            cfg = mod.resolve_agent_config(
                service_id="agent-hawk",
                strategy=None,
                agents_manifest=manifest_path,
            )
            assert cfg.service_id == "agent-hawk"
            assert cfg.challenge_strategy == "auto-challenge"
            assert cfg.detectors == ("reentrancy",)
        finally:
            __import__("sys").path = sys_path_backup

    def test_resolve_all_agents(self, tmp_path: Path):
        manifest = {
            "schema_version": "agent-personas/v1",
            "agents": [
                {
                    "service_id": "proof-of-audit-auditor",
                    "name": "Primary",
                    "challenge_strategy": "silent-monitor",
                    "detectors": ["*"],
                    "profile": "default",
                    "runtime_mode": "hybrid",
                    "capabilities": ["audit_contract"],
                    "identity": {"agent_id": 0, "operator": "T", "anvil_account_index": 0},
                },
                {
                    "service_id": "agent-hawk",
                    "name": "Hawk",
                    "challenge_strategy": "auto-challenge",
                    "detectors": ["reentrancy"],
                    "profile": "hawk",
                    "runtime_mode": "hybrid",
                    "capabilities": ["audit_contract"],
                    "identity": {"agent_id": 1, "operator": "T", "anvil_account_index": 1},
                },
                {
                    "service_id": "agent-sentinel",
                    "name": "Sentinel",
                    "challenge_strategy": "flag-for-review",
                    "detectors": ["access_control"],
                    "profile": "sentinel",
                    "runtime_mode": "hybrid",
                    "capabilities": ["audit_contract"],
                    "identity": {"agent_id": 2, "operator": "T", "anvil_account_index": 2},
                },
            ],
        }
        manifest_path = tmp_path / "agents.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cross_agent_watcher",
            str(Path(__file__).resolve().parent.parent.parent / "scripts" / "cross_agent_watcher.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        configs = mod.resolve_all_agents(manifest_path)
        assert len(configs) == 2  # excludes primary
        sids = [c.service_id for c in configs]
        assert "proof-of-audit-auditor" not in sids
        assert "agent-hawk" in sids
        assert "agent-sentinel" in sids
