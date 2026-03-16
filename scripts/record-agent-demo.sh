#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v asciinema >/dev/null 2>&1; then
  echo "asciinema is not installed. Install it first, then rerun this script." >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-${PYTHON:-python3}}"
CAST_PATH="${CAST_PATH:-$REPO_ROOT/docs/assets/proof-of-audit-agent-demo.cast}"
API_URL="${PROOF_OF_AUDIT_API_URL:-http://127.0.0.1:8080}"
FIXTURE_ID="${FIXTURE_ID:-clean-vault}"
IDLE_LIMIT="${IDLE_LIMIT:-1.5}"
TITLE="${TITLE:-Proof-of-Audit — Agent Trust Loop}"

mkdir -p "$(dirname "$CAST_PATH")"

TYPING_SPEED="${TYPING_SPEED:-fast}"

asciinema rec \
  --overwrite \
  --cols 120 \
  --rows 36 \
  --idle-time-limit "$IDLE_LIMIT" \
  --title "$TITLE" \
  "$CAST_PATH" \
  --command "$PYTHON_BIN ./scripts/run_agent_demo.py --api-url $API_URL --fixture-id $FIXTURE_ID --typing-speed $TYPING_SPEED"

echo "Wrote cast to $CAST_PATH"

if [[ "${ASCIINEMA_UPLOAD:-0}" == "1" ]]; then
  asciinema upload "$CAST_PATH"
fi
