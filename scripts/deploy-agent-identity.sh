#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONTRACTS_DIR="${ROOT_DIR}/contracts"
PYTHON_BIN="${PYTHON_BIN:-python3}"

NETWORK="${PROOF_OF_AUDIT_IDENTITY_NETWORK:-${PROOF_OF_AUDIT_DEPLOY_NETWORK:-base-sepolia}}"
CHAIN_ID="${PROOF_OF_AUDIT_IDENTITY_CHAIN_ID:-${PROOF_OF_AUDIT_DEPLOY_CHAIN_ID:-84532}}"
RPC_URL="${PROOF_OF_AUDIT_IDENTITY_RPC_URL:-${PROOF_OF_AUDIT_DEPLOY_RPC_URL:-${BASE_SEPOLIA_RPC_URL:-}}}"
MANIFEST_FILE="${PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE:-${ROOT_DIR}/deployments/${NETWORK}.json}"
AUDITOR_MANIFEST_FILE="${PROOF_OF_AUDIT_AGENT_MANIFEST_FILE:-${ROOT_DIR}/agent/proof_of_audit_agent/auditor_manifest.json}"
AUDITOR_PUBLISHED_REGISTRATION_FILE="${PROOF_OF_AUDIT_AUDITOR_PUBLISHED_REGISTRATION_FILE:-${ROOT_DIR}/docs/registrations/proof-of-audit-auditor.json}"
AUDITOR_REGISTRATION_URI="${PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI:-https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json}"
AUDITOR_PUBLIC_WEB_URL="${PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL:-https://github.com/akoita/proof-of-audit}"
AUDITOR_PUBLIC_API_URL="${PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL:-}"

DEPLOYER_PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY:-}"

: "${RPC_URL:?PROOF_OF_AUDIT_IDENTITY_RPC_URL or PROOF_OF_AUDIT_DEPLOY_RPC_URL or BASE_SEPOLIA_RPC_URL must be set}"
: "${DEPLOYER_PRIVATE_KEY:?DEPLOYER_PRIVATE_KEY must be set}"

DEFAULT_DEPLOYER_ADDRESS="$(cast wallet address --private-key "${DEPLOYER_PRIVATE_KEY}")"
AGENT_REGISTRY_ADMIN="${PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN:-${DEFAULT_DEPLOYER_ADDRESS}}"
AGENT_REGISTRY_ADMIN_PRIVATE_KEY="${PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN_PRIVATE_KEY:-${PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY:-${DEPLOYER_PRIVATE_KEY}}}"
AUDITOR_OWNER="${PROOF_OF_AUDIT_AUDITOR_OWNER:-${PROOF_OF_AUDIT_ARBITER:-${AGENT_REGISTRY_ADMIN:-}}}"

: "${AGENT_REGISTRY_ADMIN:?PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN must be set}"
: "${AGENT_REGISTRY_ADMIN_PRIVATE_KEY:?PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN_PRIVATE_KEY, PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY, or DEPLOYER_PRIVATE_KEY must be set}"
: "${AUDITOR_OWNER:?PROOF_OF_AUDIT_AUDITOR_OWNER or PROOF_OF_AUDIT_ARBITER must be set}"
: "${AUDITOR_REGISTRATION_URI:?PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI must be set}"

DEPLOY_BROADCAST_FILE="${CONTRACTS_DIR}/broadcast/DeployAgentIdentityRegistry.s.sol/${CHAIN_ID}/run-latest.json"

cd "${CONTRACTS_DIR}"

PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN="${AGENT_REGISTRY_ADMIN}" \
forge script script/DeployAgentIdentityRegistry.s.sol:DeployAgentIdentityRegistry \
  --rpc-url "${RPC_URL}" \
  --private-key "${DEPLOYER_PRIVATE_KEY}" \
  --broadcast

read -r REGISTRY_ADDRESS REGISTRY_DEPLOY_TX_HASH < <(
  "${PYTHON_BIN}" - "${DEPLOY_BROADCAST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for tx in payload.get("transactions", []):
    if tx.get("transactionType") == "CREATE" and tx.get("contractName") == "AgentIdentityRegistry":
        print(tx.get("contractAddress") or "", tx.get("hash") or "")
        raise SystemExit(0)
raise SystemExit("Could not find deployed AgentIdentityRegistry address in broadcast output")
PY
)

cast code "${REGISTRY_ADDRESS}" --rpc-url "${RPC_URL}" >/dev/null

REGISTER_TX_HASH="$(
  cast send "${REGISTRY_ADDRESS}" \
    "registerAgent(address,string)" \
    "${AUDITOR_OWNER}" \
    "${AUDITOR_REGISTRATION_URI}" \
    --rpc-url "${RPC_URL}" \
    --private-key "${AGENT_REGISTRY_ADMIN_PRIVATE_KEY}" \
    --json \
  | "${PYTHON_BIN}" -c 'import json, sys; payload = json.load(sys.stdin); print(payload.get("transactionHash") or payload.get("txHash") or payload.get("hash") or "")'
)"

if [[ -z "${REGISTER_TX_HASH}" ]]; then
  echo "Could not parse registerAgent transaction hash" >&2
  exit 1
fi

AGENT_ID="$(cast call "${REGISTRY_ADDRESS}" "nextAgentId()(uint256)" --rpc-url "${RPC_URL}")"
REGISTERED_OWNER="$(cast call "${REGISTRY_ADDRESS}" "ownerOf(uint256)(address)" "${AGENT_ID}" --rpc-url "${RPC_URL}")"
REGISTERED_URI="$(cast call "${REGISTRY_ADDRESS}" "tokenURI(uint256)(string)" "${AGENT_ID}" --rpc-url "${RPC_URL}")"
REGISTERED_URI="${REGISTERED_URI#\"}"
REGISTERED_URI="${REGISTERED_URI%\"}"

if [[ "${REGISTERED_OWNER,,}" != "${AUDITOR_OWNER,,}" ]]; then
  echo "Registered owner mismatch: expected ${AUDITOR_OWNER}, got ${REGISTERED_OWNER}" >&2
  exit 1
fi

if [[ "${REGISTERED_URI}" != "${AUDITOR_REGISTRATION_URI}" ]]; then
  echo "Registered URI mismatch: expected ${AUDITOR_REGISTRATION_URI}, got ${REGISTERED_URI}" >&2
  exit 1
fi

cd "${ROOT_DIR}"

REGISTRATION_SCRIPT_ARGS=(
  "${ROOT_DIR}/scripts/write-published-registration.py"
  --manifest-file "${AUDITOR_MANIFEST_FILE}"
  --deployment-manifest-file "${MANIFEST_FILE}"
  --output-file "${AUDITOR_PUBLISHED_REGISTRATION_FILE}"
  --registration-uri "${AUDITOR_REGISTRATION_URI}"
  --public-web-url "${AUDITOR_PUBLIC_WEB_URL}"
  --agent-id "${AGENT_ID}"
  --agent-registry "${REGISTRY_ADDRESS}"
)

if [[ -n "${AUDITOR_PUBLIC_API_URL}" ]]; then
  REGISTRATION_SCRIPT_ARGS+=(--public-api-base-url "${AUDITOR_PUBLIC_API_URL}")
fi

"${PYTHON_BIN}" "${REGISTRATION_SCRIPT_ARGS[@]}"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/write-release-manifest.py" \
  --manifest-file "${MANIFEST_FILE}" \
  --registration-document-uri "${AUDITOR_REGISTRATION_URI}" \
  --registration-document-file "${AUDITOR_PUBLISHED_REGISTRATION_FILE}" \
  --registration-source-manifest "${AUDITOR_MANIFEST_FILE}" \
  --auditor-identity-registry-address "${REGISTRY_ADDRESS}" \
  --auditor-identity-agent-id "${AGENT_ID}" \
  --auditor-identity-owner "${AUDITOR_OWNER}" \
  --auditor-identity-admin "${AGENT_REGISTRY_ADMIN}" \
  --auditor-identity-registration-uri "${AUDITOR_REGISTRATION_URI}" \
  --auditor-identity-deploy-tx-hash "${REGISTRY_DEPLOY_TX_HASH}" \
  --auditor-identity-register-tx-hash "${REGISTER_TX_HASH}"

echo
echo "Auditor identity registration complete."
echo "Network: ${NETWORK} (chain ${CHAIN_ID})"
echo "Registry: ${REGISTRY_ADDRESS}"
echo "Agent ID: ${AGENT_ID}"
echo "Owner: ${AUDITOR_OWNER}"
echo "Registration URI: ${AUDITOR_REGISTRATION_URI}"
echo "Manifest: ${MANIFEST_FILE}"
