#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PROJECT_PYENV_VERSION="${PROOF_OF_AUDIT_PYENV_VERSION:-proof-of-audit-3.12}"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="${PYTHON_BIN}"
elif [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="${PYTHON}"
elif command -v pyenv >/dev/null 2>&1 && [[ -n "${PYENV_VERSION:-}" ]]; then
  PYTHON_BIN="$(pyenv which python)"
elif command -v pyenv >/dev/null 2>&1 \
  && pyenv versions --bare 2>/dev/null | grep -qx "${PROJECT_PYENV_VERSION}"; then
  # Git hooks run without the interactive shell env; resolve the project
  # virtualenv explicitly instead of falling through to the global python.
  PYTHON_BIN="$(PYENV_VERSION="${PROJECT_PYENV_VERSION}" pyenv which python)"
else
  PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" ./scripts/run_pre_commit_security_audit.py "$@"
