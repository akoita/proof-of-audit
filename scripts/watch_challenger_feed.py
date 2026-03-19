#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen


def fetch_feed(api_base: str, limit: int) -> list[dict[str, object]]:
    query = urlencode({"limit": limit})
    url = f"{api_base.rstrip('/')}/challenger-feed?{query}"
    with urlopen(url) as response:  # noqa: S310 - caller provides the API URL intentionally
        payload = json.loads(response.read().decode("utf-8"))
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def format_event(item: dict[str, object]) -> str:
    event_timestamp = str(item.get("event_timestamp") or "unknown-time")
    event_kind = str(item.get("event_kind") or "unknown-event")
    service_id = str(item.get("service_id") or "unknown-service")
    target_contract = str(item.get("target_contract") or "unknown-target")
    state = str(item.get("current_state") or "unknown-state")
    summary = str(item.get("summary") or "")
    return (
        f"[{event_timestamp}] {event_kind} "
        f"service={service_id} target={target_contract} state={state} summary={summary}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll the Proof-of-Audit challenger feed and print new lifecycle events."
    )
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8080",
        help="Base URL for the Proof-of-Audit API.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many recent feed items to fetch on each poll.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Polling interval in seconds.",
    )
    args = parser.parse_args()

    seen: set[str] = set()
    while True:
        for item in reversed(fetch_feed(args.api_base, args.limit)):
            event_id = str(item.get("event_id") or "")
            if not event_id or event_id in seen:
                continue
            print(format_event(item), flush=True)
            seen.add(event_id)
        time.sleep(max(args.interval, 1))


if __name__ == "__main__":
    raise SystemExit(main())
