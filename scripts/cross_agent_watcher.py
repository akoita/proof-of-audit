#!/usr/bin/env python3
"""Cross-agent claim watcher — polls the challenger feed and reacts.

Usage:

    # Single agent watching with auto-challenge
    python scripts/cross_agent_watcher.py \
        --api-base http://127.0.0.1:8080 \
        --service-id agent-reentrancy-hawk \
        --strategy auto-challenge

    # Load agent config from agents.json persona manifest
    python scripts/cross_agent_watcher.py \
        --api-base http://127.0.0.1:8080 \
        --agents-manifest demo/agents.json \
        --service-id agent-reentrancy-hawk

    # Watch all non-primary agents from the manifest (multi-watcher)
    python scripts/cross_agent_watcher.py \
        --api-base http://127.0.0.1:8080 \
        --agents-manifest demo/agents.json \
        --all-agents

The watcher discovers newly published audit claims from *other* agents,
re-analyzes the same contract, and reacts based on the watching agent's
challenge_strategy:

- auto-challenge:  submit challenge with evidence if findings diverge
- flag-for-review: log divergences for human review
- silent-monitor:  observe claims without action
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Allow importing from the agent package when running from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "agent"))

from proof_of_audit_agent.claim_watcher import (  # noqa: E402
    ClaimWatcher,
    WatcherAgentConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("cross-agent-watcher")


def load_personas(manifest_path: Path) -> list[dict[str, object]]:
    text = manifest_path.read_text(encoding="utf-8")
    data = json.loads(text)
    return list(data.get("agents", []))


def resolve_agent_config(
    *,
    service_id: str,
    strategy: str | None,
    agents_manifest: Path | None,
) -> WatcherAgentConfig:
    """Resolve a WatcherAgentConfig from CLI args and optional manifest."""
    if agents_manifest and agents_manifest.exists():
        for persona in load_personas(agents_manifest):
            if str(persona.get("service_id")) == service_id:
                cfg = WatcherAgentConfig.from_persona(persona)
                if strategy:
                    cfg = WatcherAgentConfig(
                        service_id=cfg.service_id,
                        name=cfg.name,
                        challenge_strategy=strategy,
                        detectors=cfg.detectors,
                    )
                return cfg

    return WatcherAgentConfig(
        service_id=service_id,
        name=service_id,
        challenge_strategy=strategy or "silent-monitor",
    )


def resolve_all_agents(
    agents_manifest: Path,
    strategy_override: str | None = None,
) -> list[WatcherAgentConfig]:
    """Resolve all non-primary agent configs from the manifest."""
    configs: list[WatcherAgentConfig] = []
    for persona in load_personas(agents_manifest):
        sid = str(persona.get("service_id") or "")
        if not sid or sid == "proof-of-audit-auditor":
            continue
        cfg = WatcherAgentConfig.from_persona(persona)
        if strategy_override:
            cfg = WatcherAgentConfig(
                service_id=cfg.service_id,
                name=cfg.name,
                challenge_strategy=strategy_override,
                detectors=cfg.detectors,
            )
        configs.append(cfg)
    return configs


def run_watchers(
    watchers: list[ClaimWatcher],
    *,
    interval: int,
    limit: int,
    once: bool = False,
) -> int:
    """Run all watchers in a polling loop (round-robin)."""
    logger.info(
        "Starting %d watcher(s), interval=%ds, limit=%d",
        len(watchers),
        interval,
        limit,
    )
    for w in watchers:
        logger.info(
            "  → %s (strategy=%s, detectors=%s)",
            w.agent_config.service_id,
            w.agent_config.challenge_strategy,
            ",".join(w.agent_config.detectors) or "*",
        )

    total_processed = 0
    try:
        while True:
            for watcher in watchers:
                results = watcher.poll_and_react(limit=limit)
                for r in results:
                    total_processed += 1
                    tag = r.action_taken.upper()
                    diverge_info = (
                        f" ({len(r.divergences)} divergences)"
                        if r.divergences
                        else ""
                    )
                    logger.info(
                        "[%s] %s claim %s from %s on %s%s",
                        r.watcher_service_id,
                        tag,
                        r.claim_event_id,
                        r.claim_service_id,
                        r.target_contract,
                        diverge_info,
                    )

            if once:
                break

            time.sleep(max(interval, 1))

    except KeyboardInterrupt:
        logger.info("Interrupted. Processed %d claims total.", total_processed)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-agent claim watcher — react to published audit claims.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8080",
        help="Base URL for the Proof-of-Audit API.",
    )
    parser.add_argument(
        "--service-id",
        help="Service ID of the watching agent. Required unless --all-agents is set.",
    )
    parser.add_argument(
        "--strategy",
        choices=["auto-challenge", "flag-for-review", "silent-monitor"],
        help="Override the challenge strategy (default: from manifest or silent-monitor).",
    )
    parser.add_argument(
        "--agents-manifest",
        type=Path,
        help="Path to demo/agents.json for loading agent persona config.",
    )
    parser.add_argument(
        "--all-agents",
        action="store_true",
        help="Run watchers for all non-primary agents from the manifest.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Polling interval in seconds (default: 15).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max feed items per poll (default: 50).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll cycle then exit.",
    )
    args = parser.parse_args()

    # Resolve watcher configs
    watchers: list[ClaimWatcher] = []

    if args.all_agents:
        if not args.agents_manifest:
            print("ERROR: --all-agents requires --agents-manifest", file=sys.stderr)
            return 1
        if not args.agents_manifest.exists():
            print(
                f"ERROR: agents manifest not found: {args.agents_manifest}",
                file=sys.stderr,
            )
            return 1
        configs = resolve_all_agents(args.agents_manifest, args.strategy)
        for cfg in configs:
            watchers.append(ClaimWatcher(api_base_url=args.api_base, agent_config=cfg))
    elif args.service_id:
        cfg = resolve_agent_config(
            service_id=args.service_id,
            strategy=args.strategy,
            agents_manifest=args.agents_manifest,
        )
        watchers.append(ClaimWatcher(api_base_url=args.api_base, agent_config=cfg))
    else:
        print(
            "ERROR: specify --service-id or --all-agents",
            file=sys.stderr,
        )
        return 1

    if not watchers:
        print("ERROR: no watchers configured", file=sys.stderr)
        return 1

    return run_watchers(
        watchers,
        interval=args.interval,
        limit=args.limit,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
