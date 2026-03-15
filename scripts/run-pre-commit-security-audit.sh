#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="${PYTHON_BIN}"
elif [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="${PYTHON}"
elif command -v pyenv >/dev/null 2>&1 && [[ -n "${PYENV_VERSION:-}" ]]; then
  PYTHON_BIN="$(pyenv which python)"
else
  PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" ./scripts/run_pre_commit_security_audit.py "$@"
