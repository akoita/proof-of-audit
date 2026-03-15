#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONTRACTS_DIR="${ROOT_DIR}/contracts"
PYTHON_BIN="${PYTHON_BIN:-python3}"

RPC_URL="${ANVIL_RPC_URL:-http://127.0.0.1:8545}"
CHAIN_ID="${ANVIL_CHAIN_ID:-31337}"
NETWORK="${PROOF_OF_AUDIT_NETWORK:-anvil-local}"
MANIFEST_FILE="${ROOT_DIR}/deployments/localhost.json"
API_ENV_FILE="${ROOT_DIR}/api/.env.local"
LOCAL_PRIVATE_KEY="${LOCAL_DEPLOYER_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
LOCAL_OWNER_ADDRESS="${LOCAL_OWNER_ADDRESS:-$(cast wallet address --private-key "${LOCAL_PRIVATE_KEY}")}"
REGISTRATION_URI="${PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI:-https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json}"
VALIDATION_BROADCAST_FILE="${CONTRACTS_DIR}/broadcast/DeployValidationRegistryAdapter.s.sol/${CHAIN_ID}/run-latest.json"

cd "${ROOT_DIR}"

./scripts/deploy-local.sh
./scripts/deploy-demo-fixtures.sh

PROOF_OF_AUDIT_IDENTITY_NETWORK="${NETWORK}" \
PROOF_OF_AUDIT_IDENTITY_CHAIN_ID="${CHAIN_ID}" \
PROOF_OF_AUDIT_IDENTITY_RPC_URL="${RPC_URL}" \
PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE="${MANIFEST_FILE}" \
PROOF_OF_AUDIT_ERC8004_IDENTITY_MODE="custom" \
PROOF_OF_AUDIT_ARBITER="${LOCAL_OWNER_ADDRESS}" \
PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI="${REGISTRATION_URI}" \
PROOF_OF_AUDIT_AUDITOR_OWNER="${LOCAL_OWNER_ADDRESS}" \
PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY="${LOCAL_PRIVATE_KEY}" \
DEPLOYER_PRIVATE_KEY="${LOCAL_PRIVATE_KEY}" \
PYTHON_BIN="${PYTHON_BIN}" \
./scripts/deploy-agent-identity.sh

read -r AGENT_REGISTRY_ADDRESS AUDITOR_AGENT_ID < <(
  "${PYTHON_BIN}" - "${MANIFEST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
identity = manifest.get("auditor_identity", {})
print(identity.get("registry_address") or "", identity.get("agent_id") or "")
PY
)

if [[ -z "${AGENT_REGISTRY_ADDRESS}" || -z "${AUDITOR_AGENT_ID}" ]]; then
  echo "Could not read local auditor identity registration from ${MANIFEST_FILE}" >&2
  exit 1
fi

cd "${CONTRACTS_DIR}"

PROOF_OF_AUDIT_VALIDATION_IDENTITY_REGISTRY="${AGENT_REGISTRY_ADDRESS}" \
forge script script/DeployValidationRegistryAdapter.s.sol:DeployValidationRegistryAdapter \
  --rpc-url "${RPC_URL}" \
  --private-key "${LOCAL_PRIVATE_KEY}" \
  --broadcast

VALIDATION_REGISTRY_ADDRESS="$(
  "${PYTHON_BIN}" - "${VALIDATION_BROADCAST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for tx in payload.get("transactions", []):
    if tx.get("transactionType") == "CREATE" and tx.get("contractName") == "ValidationRegistryAdapter":
        print(tx.get("contractAddress") or "")
        raise SystemExit(0)
raise SystemExit("Could not find deployed ValidationRegistryAdapter address in broadcast output")
PY
)"

cd "${ROOT_DIR}"

"${PYTHON_BIN}" ./scripts/write-release-manifest.py \
  --manifest-file "${MANIFEST_FILE}" \
  --validation-bridge-registry-address "${VALIDATION_REGISTRY_ADDRESS}" \
  --validation-bridge-source "project-local-custom"

"${PYTHON_BIN}" ./scripts/write-local-agent-stack-config.py \
  --env-file "${API_ENV_FILE}" \
  --auditor-agent-id "${AUDITOR_AGENT_ID}" \
  --auditor-agent-registry "${AGENT_REGISTRY_ADDRESS}" \
  --auditor-owner-private-key "${LOCAL_PRIVATE_KEY}" \
  --validation-registry-address "${VALIDATION_REGISTRY_ADDRESS}" \
  --validator-private-key "${LOCAL_PRIVATE_KEY}" \
  --validator-address "${LOCAL_OWNER_ADDRESS}"

echo
echo "Local agent demo stack complete."
echo "Auditor agent id: ${AUDITOR_AGENT_ID}"
echo "Identity registry: ${AGENT_REGISTRY_ADDRESS}"
echo "Validation registry: ${VALIDATION_REGISTRY_ADDRESS}"
echo "API env updated: ${API_ENV_FILE}"
