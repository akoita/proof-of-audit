#!/usr/bin/env python3
"""Multi-agent demo orchestrator — submit audits, publish claims, show results.

This script orchestrates the audit lifecycle across multiple agent personas:
1. Reads agent personas from demo/agents.json
2. Submits audit requests from each agent against demo contracts
3. Publishes claims from each agent
4. Reports summary with colored output

Usage:
    # Full lifecycle
    python scripts/run-multi-agent-demo.py \
        --api-base http://127.0.0.1:8080 \
        --agents-manifest demo/agents.json \
        --mode local

    # Summary only (assumes audits already submitted)
    python scripts/run-multi-agent-demo.py \
        --api-base http://127.0.0.1:8080 \
        --agents-manifest demo/agents.json \
        --summary-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import urllib.request
import urllib.error

# ──────────────────────────────────────────────────
# Colors
# ──────────────────────────────────────────────────

NO_COLOR = os.environ.get("NO_COLOR", "")


class C:
    """ANSI color codes (disabled when NO_COLOR is set)."""

    RED = "" if NO_COLOR else "\033[0;31m"
    GREEN = "" if NO_COLOR else "\033[0;32m"
    YELLOW = "" if NO_COLOR else "\033[1;33m"
    BLUE = "" if NO_COLOR else "\033[0;34m"
    CYAN = "" if NO_COLOR else "\033[0;36m"
    MAGENTA = "" if NO_COLOR else "\033[0;35m"
    BOLD = "" if NO_COLOR else "\033[1m"
    DIM = "" if NO_COLOR else "\033[2m"
    NC = "" if NO_COLOR else "\033[0m"


def banner(msg: str) -> None:
    print(f"\n{C.CYAN}{C.BOLD}{'═' * 60}{C.NC}")
    print(f"{C.CYAN}{C.BOLD}  {msg}{C.NC}")
    print(f"{C.CYAN}{C.BOLD}{'═' * 60}{C.NC}\n")


def step(msg: str) -> None:
    print(f"{C.BLUE}[STEP]{C.NC} {C.BOLD}{msg}{C.NC}")


def ok(msg: str) -> None:
    print(f"{C.GREEN}  ✓{C.NC} {msg}")


def warn(msg: str) -> None:
    print(f"{C.YELLOW}  ⚠{C.NC} {msg}")


def fail(msg: str) -> None:
    print(f"{C.RED}  ✗{C.NC} {msg}")


def info(msg: str) -> None:
    print(f"{C.DIM}    {msg}{C.NC}")


# ──────────────────────────────────────────────────
# API Client
# ──────────────────────────────────────────────────


def api_get(base: str, path: str) -> dict | list | None:
    """GET from the API and return parsed JSON."""
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    try:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        fail(f"GET {path} → {e.code}")
        return None
    except Exception as e:
        fail(f"GET {path} → {e}")
        return None


def api_post(base: str, path: str, body: dict) -> dict | None:
    """POST JSON to the API and return parsed JSON."""
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode()[:200]
        except Exception:
            pass
        fail(f"POST {path} → {e.code}: {body_text}")
        return None
    except Exception as e:
        fail(f"POST {path} → {e}")
        return None


# ──────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────


@dataclass
class AgentResult:
    """Result of an audit submission from one agent."""

    service_id: str
    name: str
    profile: str
    fixture_id: str
    audit_id: str = ""
    status: str = ""
    finding_count: int = 0
    max_severity: str = ""
    summary: str = ""
    published: bool = False
    publish_tx: str = ""
    error: str = ""


@dataclass
class DemoState:
    """Tracks the overall demo state."""

    agents: list[dict] = field(default_factory=list)
    results: list[AgentResult] = field(default_factory=list)
    challenges: list[dict] = field(default_factory=list)


# ──────────────────────────────────────────────────
# Demo Fixture Discovery
# ──────────────────────────────────────────────────


DEMO_FIXTURES = [
    "vulnerable-bank",
    "admin-setter",
    "dual-risk-vault",
]


def discover_fixtures(api_base: str) -> list[str]:
    """Discover available demo fixtures from the API."""
    data = api_get(api_base, "/config")
    if data and isinstance(data, dict):
        fixtures = data.get("demo_fixtures", [])
        if fixtures:
            return [f.get("fixture_id", f) if isinstance(f, dict) else str(f) for f in fixtures]
    return DEMO_FIXTURES


# ──────────────────────────────────────────────────
# Submit & Publish
# ──────────────────────────────────────────────────


def submit_audit(
    api_base: str,
    *,
    service_id: str,
    fixture_id: str,
) -> dict | None:
    """Submit an audit for a demo fixture."""
    body = {
        "input_kind": "demo_fixture",
        "service_id": service_id,
        "fixture_id": fixture_id,
        "submitted_by": f"demo-orchestrator/{service_id}",
    }
    return api_post(api_base, "/audits", body)


def publish_audit(api_base: str, audit_id: str) -> dict | None:
    """Publish an audit claim."""
    return api_post(api_base, f"/audits/{audit_id}/publish", {})


# ──────────────────────────────────────────────────
# Summary Table
# ──────────────────────────────────────────────────

SEVERITY_COLORS = {
    "critical": C.RED,
    "high": C.RED,
    "medium": C.YELLOW,
    "low": C.GREEN,
    "informational": C.DIM,
    "none": C.DIM,
}


def print_summary(state: DemoState) -> None:
    """Print a colored summary table of all demo results."""
    banner("Multi-Agent Demo Summary")

    # Agent results
    if state.results:
        header = f"{'Agent':<30} {'Profile':<25} {'Fixture':<20} {'Findings':>8} {'Severity':<12} {'Published':<10}"
        print(f"{C.BOLD}{header}{C.NC}")
        print("─" * 110)

        for r in state.results:
            if r.error:
                status = f"{C.RED}ERROR{C.NC}"
                row = f"{r.name:<30} {r.profile:<25} {r.fixture_id:<20} {'—':>8} {'—':<12} {status:<10}"
            else:
                sev_color = SEVERITY_COLORS.get(r.max_severity.lower(), C.NC)
                pub_icon = f"{C.GREEN}✓{C.NC}" if r.published else f"{C.DIM}—{C.NC}"
                row = (
                    f"{r.name:<30} {r.profile:<25} {r.fixture_id:<20} "
                    f"{r.finding_count:>8} {sev_color}{r.max_severity:<12}{C.NC} {pub_icon:<10}"
                )
            print(row)

        print("─" * 110)

    # Stats
    total = len(state.results)
    published = sum(1 for r in state.results if r.published)
    errored = sum(1 for r in state.results if r.error)
    findings_total = sum(r.finding_count for r in state.results)

    print()
    print(f"  {C.BOLD}Total audits:{C.NC}    {total}")
    print(f"  {C.BOLD}Published:{C.NC}       {published}")
    print(f"  {C.BOLD}Errors:{C.NC}          {errored}")
    print(f"  {C.BOLD}Total findings:{C.NC}  {findings_total}")

    if state.challenges:
        print(f"  {C.BOLD}Challenges:{C.NC}      {len(state.challenges)}")
    print()


# ──────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────


def load_agents(manifest_path: Path) -> list[dict]:
    """Load agent personas from the manifest file."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(data.get("agents", []))


def run_summary_only(api_base: str, agents: list[dict]) -> int:
    """Fetch existing audits and print a summary."""
    state = DemoState(agents=agents)

    data = api_get(api_base, "/audits?limit=100")
    if not data:
        fail("Could not fetch audits from API")
        return 1

    audits = data if isinstance(data, list) else data.get("audits", [])
    agent_ids = {a["service_id"] for a in agents}

    for audit in audits:
        sid = audit.get("service_id", audit.get("auditor_service", {}).get("service_id", ""))
        if sid not in agent_ids:
            continue

        agent = next((a for a in agents if a["service_id"] == sid), {})
        report = audit.get("report", {})
        onchain = audit.get("onchain", {})

        result = AgentResult(
            service_id=sid,
            name=agent.get("name", sid),
            profile=agent.get("profile", "unknown"),
            fixture_id=audit.get("submission", {}).get("fixture_id", "?"),
            audit_id=audit.get("id", ""),
            status=audit.get("state", ""),
            finding_count=report.get("finding_count", 0),
            max_severity=report.get("max_severity", "none"),
            summary=report.get("summary", ""),
            published=bool(onchain.get("publish_tx_hash")),
            publish_tx=onchain.get("publish_tx_hash", ""),
        )
        state.results.append(result)

    # Check for challenges
    feed = api_get(api_base, "/challenger-feed?limit=100")
    if feed:
        events = feed if isinstance(feed, list) else feed.get("events", [])
        state.challenges = [
            e for e in events
            if isinstance(e, dict) and e.get("event_kind") in ("challenge_opened", "challenge_resolved")
        ]

    print_summary(state)
    return 0


def run_lifecycle(
    api_base: str,
    agents: list[dict],
    mode: str,
) -> int:
    """Run the full audit lifecycle for all agents."""
    state = DemoState(agents=agents)

    fixtures = discover_fixtures(api_base)
    if not fixtures:
        warn("No fixtures discovered, using defaults")
        fixtures = DEMO_FIXTURES

    ok(f"Discovered {len(fixtures)} fixtures: {', '.join(fixtures)}")

    # ── Phase 1: Submit audits ──
    banner("Phase 1: Submit Audits")

    # Assign a primary fixture to each agent, cycling through available fixtures.
    for i, agent in enumerate(agents):
        service_id = agent["service_id"]
        name = agent["name"]
        profile = agent.get("profile", "unknown")
        fixture_id = fixtures[i % len(fixtures)]

        step(f"Submitting audit: {name} → {fixture_id}")

        result = AgentResult(
            service_id=service_id,
            name=name,
            profile=profile,
            fixture_id=fixture_id,
        )

        resp = submit_audit(api_base, service_id=service_id, fixture_id=fixture_id)
        if resp and resp.get("id"):
            result.audit_id = resp["id"]
            report = resp.get("report", {})
            result.status = resp.get("state", "draft")
            result.finding_count = report.get("finding_count", 0)
            result.max_severity = report.get("max_severity", "none")
            result.summary = report.get("summary", "")
            ok(f"Audit {result.audit_id[:12]}… → {result.finding_count} findings, {result.max_severity}")
        else:
            result.error = "submission failed"
            fail(f"Submission failed for {name}")

        state.results.append(result)
        time.sleep(0.3)

    # ── Phase 2: Publish claims ──
    banner("Phase 2: Publish Claims")

    for result in state.results:
        if result.error or not result.audit_id:
            warn(f"Skipping {result.name} (no audit)")
            continue

        step(f"Publishing: {result.name} ({result.audit_id[:12]}…)")
        resp = publish_audit(api_base, result.audit_id)
        if resp:
            onchain = resp.get("onchain", {})
            tx = onchain.get("publish_tx_hash", "")
            if tx:
                result.published = True
                result.publish_tx = tx
                ok(f"Published → tx {tx[:16]}…")
            else:
                warn(f"Published but no tx hash returned")
                result.published = True
        else:
            warn(f"Publish failed for {result.name}")

        time.sleep(0.3)

    # ── Phase 3: Summary ──
    print_summary(state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Multi-agent demo orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("PROOF_OF_AUDIT_API_URL", "http://127.0.0.1:8080"),
        help="Base URL for the Proof-of-Audit API.",
    )
    parser.add_argument(
        "--agents-manifest",
        type=Path,
        default=Path("demo/agents.json"),
        help="Path to the agents persona manifest.",
    )
    parser.add_argument(
        "--mode",
        choices=["local", "hosted"],
        default="local",
        help="Demo mode (local or hosted).",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print the current state summary (no new submissions).",
    )
    parser.add_argument(
        "--skip-watchers",
        action="store_true",
        help="Skip starting cross-agent watchers.",
    )
    args = parser.parse_args()

    if not args.agents_manifest.exists():
        fail(f"Agents manifest not found: {args.agents_manifest}")
        return 1

    agents = load_agents(args.agents_manifest)
    if not agents:
        fail("No agents found in manifest")
        return 1

    ok(f"Loaded {len(agents)} agent personas from {args.agents_manifest}")

    if args.summary_only:
        return run_summary_only(args.api_base, agents)

    return run_lifecycle(args.api_base, agents, args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
