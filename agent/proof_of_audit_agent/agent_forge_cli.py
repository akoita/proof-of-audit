from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from proof_of_audit_agent.live_auditor import analyze_repository


REPORT_FILE = ".proof-of-audit/agent-report.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Source-based live auditor used by Proof-of-Audit."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Analyze a repository and write an audit report.")
    run_parser.add_argument("--task", required=True)
    run_parser.add_argument("--repo", required=True)
    run_parser.add_argument("--provider")
    run_parser.add_argument("--model")
    run_parser.add_argument("--max-iterations", type=int)
    run_parser.add_argument(
        "--detectors",
        help="Comma-separated detector families to run (e.g. reentrancy,access_control). Default: all.",
    )
    return parser


def _runs_root() -> Path:
    home = Path(os.environ.get("HOME") or Path.home())
    return home / ".agent-forge" / "runs"


def _write_run_record(*, run_id: str, repo_path: Path, state: str, error: str | None = None) -> None:
    run_dir = _runs_root() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "id": run_id,
        "repo_path": str(repo_path),
        "state": state,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if error:
        payload["error"] = error
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    repo_path = Path(args.repo).resolve()
    run_id = f"run-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"

    try:
        if not repo_path.exists():
            raise ValueError(f"repository path does not exist: {repo_path}")
        if not repo_path.is_dir():
            raise ValueError(f"repository path is not a directory: {repo_path}")

        detectors_raw = getattr(args, "detectors", None)
        detectors = (
            frozenset(d.strip() for d in detectors_raw.split(",") if d.strip())
            if detectors_raw
            else None
        )

        report = analyze_repository(repo_path, detectors=detectors)
        report_path = repo_path / REPORT_FILE
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        _write_run_record(run_id=run_id, repo_path=repo_path, state="completed")
        return 0
    except Exception as exc:
        _write_run_record(run_id=run_id, repo_path=repo_path, state="failed", error=str(exc))
        sys.stderr.write(f"{exc}\n")
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
