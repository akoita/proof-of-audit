from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = REPO_ROOT / ".tmp" / "security-audit" / "pre-commit-report.md"
TRUSTED_SOURCES = [
    {
        "name": "OpenZeppelin Skills",
        "url": "https://github.com/OpenZeppelin/openzeppelin-skills",
        "focus": "secure contract development and upgrade-oriented Solidity reviews",
    },
    {
        "name": "Pashov Skills",
        "url": "https://github.com/pashov/skills",
        "focus": "fast Solidity auditor heuristics for developer feedback loops",
    },
    {
        "name": "Trail of Bits Curated Skills",
        "url": "https://github.com/trailofbits/skills-curated",
        "focus": "reviewed security plugins and Solidity-oriented scanning guidance",
    },
]
CONTRACT_PREFIXES = ("contracts/", "demo/contracts/")
BACKEND_PREFIXES = (
    "api/proof_of_audit_api/",
    "agent/proof_of_audit_agent/",
)
BACKEND_EXACT = {
    ".env.example",
    "pyproject.toml",
}
BACKEND_SCRIPT_MARKERS = (
    "scripts/deploy-",
    "scripts/verify-",
    "scripts/write-",
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the staged-file security audit workflow for Proof-of-Audit."
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Explicit file list to classify instead of reading staged git changes.",
    )
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help="Where to write the markdown report.",
    )
    parser.add_argument(
        "--skip-commands",
        action="store_true",
        help="Build the audit plan and write the report without executing commands.",
    )
    parser.add_argument(
        "--plan-json",
        action="store_true",
        help="Print the computed audit plan as JSON.",
    )
    return parser.parse_args(argv)


def get_staged_files() -> list[str]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_contract_file(path: str) -> bool:
    return path.endswith(".sol") and path.startswith(CONTRACT_PREFIXES)


def is_backend_sensitive_file(path: str) -> bool:
    if path in BACKEND_EXACT:
        return True
    if path.startswith(BACKEND_PREFIXES):
        return True
    return path.startswith(BACKEND_SCRIPT_MARKERS)


def build_commands(files: Sequence[str], python_bin: str) -> tuple[list[str], list[dict[str, str | list[str]]]]:
    contract_files = sorted({path for path in files if is_contract_file(path)})
    backend_files = sorted({path for path in files if is_backend_sensitive_file(path)})
    commands: list[dict[str, str | list[str]]] = []

    if contract_files:
        commands.append(
            {
                "label": "contract-security-regression",
                "reason": "Solidity contracts changed",
                "command": ["forge", "test", "--root", "contracts"],
            }
        )
    if backend_files:
        commands.append(
            {
                "label": "backend-security-regression",
                "reason": "Security-sensitive backend paths changed",
                "command": [
                    python_bin,
                    "-m",
                    "pytest",
                    "agent/tests/test_worker.py",
                    "api/tests/test_app.py",
                    "api/tests/test_service.py",
                    "api/tests/test_submission_modes.py",
                    "api/tests/test_config.py",
                    "api/tests/test_erc8004_registration.py",
                    "-q",
                ],
            }
        )
    return contract_files, backend_files, commands


def write_report(
    *,
    report_path: Path,
    files: Sequence[str],
    contract_files: Sequence[str],
    backend_files: Sequence[str],
    commands: Sequence[dict[str, str | list[str]]],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Pre-commit Security Audit",
        "",
        "## Changed files",
    ]
    if files:
        lines.extend(f"- `{path}`" for path in files)
    else:
        lines.append("- no staged files detected")

    lines.extend(
        [
            "",
            "## Trigger summary",
            f"- Solidity-sensitive files: {len(contract_files)}",
            f"- Backend-sensitive files: {len(backend_files)}",
            "",
            "## Commands",
        ]
    )
    if commands:
        for entry in commands:
            cmd = " ".join(str(part) for part in entry["command"])
            lines.append(f"- `{entry['label']}`: `{cmd}`")
    else:
        lines.append("- no additional security commands required for this staged diff")

    lines.extend(["", "## Trusted source policy"])
    for source in TRUSTED_SOURCES:
        lines.append(
            f"- [{source['name']}]({source['url']}): {source['focus']}"
        )

    lines.extend(
        [
            "",
            "## Review notes",
            "- This workflow only triggers on staged Solidity and security-sensitive backend paths.",
            "- The curated sources above are the approved references for extending this gate.",
            "- The hook is intentionally local-first and does not install marketplace plugins automatically.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run_commands(commands: Sequence[dict[str, str | list[str]]]) -> int:
    for entry in commands:
        command = entry["command"]
        assert isinstance(command, list)
        print(f"[security-audit] running {entry['label']}: {' '.join(command)}")
        result = subprocess.run(command, cwd=REPO_ROOT)
        if result.returncode != 0:
            return result.returncode
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    files = args.files if args.files is not None else get_staged_files()
    report_path = Path(args.report_path)
    python_bin = str(Path(sys.executable)) if sys.executable else "python3"
    contract_files, backend_files, commands = build_commands(files, python_bin)
    write_report(
        report_path=report_path,
        files=files,
        contract_files=contract_files,
        backend_files=backend_files,
        commands=commands,
    )
    plan = {
        "files": files,
        "contract_files": contract_files,
        "backend_files": backend_files,
        "commands": commands,
        "report_path": str(report_path),
        "relevant": bool(commands),
        "trusted_sources": TRUSTED_SOURCES,
    }
    emit_status = not args.plan_json
    if args.plan_json:
        print(json.dumps(plan, indent=2))
    if args.skip_commands or not commands:
        if emit_status and not commands:
            print("[security-audit] no Solidity or backend-sensitive staged files detected")
        elif emit_status:
            print(f"[security-audit] plan written to {report_path}")
        return 0
    exit_code = run_commands(commands)
    if exit_code == 0:
        print(f"[security-audit] completed successfully; report written to {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
