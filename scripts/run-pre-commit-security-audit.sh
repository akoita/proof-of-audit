#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-${PYTHON:-python3}}"

exec "$PYTHON_BIN" ./scripts/run_pre_commit_security_audit.py "$@"
