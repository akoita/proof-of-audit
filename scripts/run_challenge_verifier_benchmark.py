#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proof_of_audit_agent.verifier_benchmark import (
    DEFAULT_BENCHMARK_CORPUS,
    run_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the replayable Challenge Verifier V2 benchmark corpus."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_BENCHMARK_CORPUS,
        help="Path to the benchmark corpus JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional file path for the structured benchmark result JSON.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    args = parser.parse_args()

    report = run_benchmark(args.corpus)
    encoded = json.dumps(report, indent=2 if args.pretty else None, sort_keys=True)
    if args.output is not None:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
