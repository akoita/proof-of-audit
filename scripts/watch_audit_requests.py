#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import time

from proof_of_audit_agent.request_participation import (
    AuditRequestMarketplaceClient,
    AuditRequestParticipationLoop,
    JsonlDecisionStore,
    ParticipationDecision,
    ParticipationPolicy,
)


def parse_eth_to_wei(value: str) -> int:
    return max(int(float(value) * 1e18), 0)


def log_decision(decision: ParticipationDecision) -> None:
    suffix = f" audit_id={decision.submitted_audit_id}" if decision.submitted_audit_id else ""
    print(
        f"[request={decision.request_id}] action={decision.action} "
        f"eligible={decision.eligible} suggested_stake_wei={decision.suggested_stake_wei} "
        f"opportunity_score_wei={decision.opportunity_score_wei} reason={decision.reason}{suffix}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll open audit requests and log participation decisions."
    )
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8080",
        help="Base URL for the Proof-of-Audit API.",
    )
    parser.add_argument(
        "--auditor-service-id",
        required=True,
        help="Auditor service ID to evaluate against request eligibility.",
    )
    parser.add_argument(
        "--decision-log",
        default=".proof-of-audit-runtime/request-decisions.jsonl",
        help="JSONL file used for idempotency and decision logging.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Polling interval in seconds.",
    )
    parser.add_argument(
        "--minimum-bounty-eth",
        default="0.0",
        help="Minimum bounty threshold in ETH.",
    )
    parser.add_argument(
        "--opportunity-cost-eth",
        default="0.0",
        help="Opportunity-cost threshold in ETH.",
    )
    parser.add_argument(
        "--max-concurrent-audits",
        type=int,
        default=2,
        help="Maximum concurrent accepted requests before new ones are skipped.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit draft audits through the API instead of staying in log-only mode.",
    )
    args = parser.parse_args()

    loop = AuditRequestParticipationLoop(
        client=AuditRequestMarketplaceClient(base_url=args.api_base),
        auditor_service_id=args.auditor_service_id,
        policy=ParticipationPolicy(
            minimum_bounty_wei=parse_eth_to_wei(args.minimum_bounty_eth),
            opportunity_cost_wei=parse_eth_to_wei(args.opportunity_cost_eth),
            max_concurrent_audits=max(args.max_concurrent_audits, 1),
        ),
        decision_store=JsonlDecisionStore(Path(args.decision_log)),
        submission_enabled=args.submit,
        logger=log_decision,
    )

    while True:
        loop.run_once()
        time.sleep(max(args.interval, 1))


if __name__ == "__main__":
    raise SystemExit(main())
