#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONTRACTS_DIR="${ROOT_DIR}/contracts"
PYTHON_BIN="${PYTHON_BIN:-python3}"

NETWORK="${PROOF_OF_AUDIT_DEPLOY_NETWORK:-base-sepolia}"
CHAIN_ID="${PROOF_OF_AUDIT_DEPLOY_CHAIN_ID:-84532}"
MANIFEST_FILE="${PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE:-${ROOT_DIR}/deployments/${NETWORK}.json}"
API_KEY="${PROOF_OF_AUDIT_VERIFY_API_KEY:-${BASESCAN_API_KEY:-}}"
DRY_RUN="${PROOF_OF_AUDIT_VERIFY_DRY_RUN:-0}"
CONTRACT_REFERENCE="${PROOF_OF_AUDIT_VERIFY_CONTRACT_REFERENCE:-src/ProofOfAudit.sol:ProofOfAudit}"

: "${API_KEY:?PROOF_OF_AUDIT_VERIFY_API_KEY or BASESCAN_API_KEY must be set}"

read -r CONTRACT_ADDRESS CONSTRUCTOR_ARGS_HEX < <(
  "${PYTHON_BIN}" - "${MANIFEST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
address = payload.get("address")
constructor_args = payload.get("constructor_args", {}).get("encoded")
if not address:
    raise SystemExit("Deployment manifest is missing contract address")
if not constructor_args:
    raise SystemExit("Deployment manifest is missing encoded constructor arguments")
print(address, constructor_args)
PY
)

VERIFY_CMD=(
  forge verify-contract
  --chain "${CHAIN_ID}"
  --watch
  --constructor-args "${CONSTRUCTOR_ARGS_HEX}"
  --etherscan-api-key "${API_KEY}"
  "${CONTRACT_ADDRESS}"
  "${CONTRACT_REFERENCE}"
)

DISPLAY_VERIFY_CMD=(
  forge verify-contract
  --chain "${CHAIN_ID}"
  --watch
  --constructor-args "${CONSTRUCTOR_ARGS_HEX}"
  --etherscan-api-key '<redacted>'
  "${CONTRACT_ADDRESS}"
  "${CONTRACT_REFERENCE}"
)

echo "Preparing verification for ${CONTRACT_ADDRESS} on ${NETWORK} (chain ${CHAIN_ID})."
printf 'Command:'
printf ' %q' "${DISPLAY_VERIFY_CMD[@]}"
printf '\n'

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "Verification dry run enabled; no remote verification request was sent."
  exit 0
fi

(
  cd "${CONTRACTS_DIR}"
  "${VERIFY_CMD[@]}"
)

VERIFIED_AT="$("${PYTHON_BIN}" - <<'PY'
from datetime import UTC, datetime
print(datetime.now(UTC).isoformat())
PY
)"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/write-release-manifest.py" \
  --manifest-file "${MANIFEST_FILE}" \
  --verification-status "verified" \
  --verification-provider "basescan" \
  --verification-command "$(printf '%q ' "${DISPLAY_VERIFY_CMD[@]}")" \
  --verified-at "${VERIFIED_AT}"

echo "Verification recorded in ${MANIFEST_FILE}."
