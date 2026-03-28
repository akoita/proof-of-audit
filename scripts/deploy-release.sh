#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONTRACTS_DIR="${ROOT_DIR}/contracts"
PYTHON_BIN="${PYTHON_BIN:-python3}"

NETWORK="${PROOF_OF_AUDIT_DEPLOY_NETWORK:-base-sepolia}"
CHAIN_ID="${PROOF_OF_AUDIT_DEPLOY_CHAIN_ID:-84532}"
RPC_URL="${PROOF_OF_AUDIT_DEPLOY_RPC_URL:-${BASE_SEPOLIA_RPC_URL:-}}"
EXPLORER_BASE_URL="${PROOF_OF_AUDIT_EXPLORER_BASE_URL:-https://sepolia.basescan.org}"
MANIFEST_FILE="${PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE:-${ROOT_DIR}/deployments/${NETWORK}.json}"
DEPLOY_VERIFY="${PROOF_OF_AUDIT_DEPLOY_VERIFY:-0}"
AUDITOR_MANIFEST_FILE="${PROOF_OF_AUDIT_AGENT_MANIFEST_FILE:-${ROOT_DIR}/agent/proof_of_audit_agent/auditor_manifest.json}"
AUDITOR_PUBLISHED_REGISTRATION_FILE="${PROOF_OF_AUDIT_AUDITOR_PUBLISHED_REGISTRATION_FILE:-${ROOT_DIR}/docs/registrations/proof-of-audit-auditor.json}"
AUDITOR_REGISTRATION_URI="${PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI:-https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json}"
AUDITOR_PUBLIC_WEB_URL="${PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL:-https://github.com/akoita/proof-of-audit}"
AUDITOR_PUBLIC_API_URL="${PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL:-}"
AUDITOR_AGENT_ID="${PROOF_OF_AUDIT_AUDITOR_AGENT_ID:-}"
AUDITOR_AGENT_REGISTRY="${PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY:-}"
VALIDATION_REGISTRY_ADDRESS="${PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS:-}"
VALIDATION_BRIDGE_SOURCE="${PROOF_OF_AUDIT_VALIDATION_BRIDGE_SOURCE:-}"

if [[ -z "${VALIDATION_REGISTRY_ADDRESS}" && "${NETWORK}" == "base-sepolia" && "${CHAIN_ID}" == "84532" ]]; then
  VALIDATION_REGISTRY_ADDRESS="0x8004B663056A597Dffe9eCcC1965A193B7388713"
fi

if [[ -z "${VALIDATION_BRIDGE_SOURCE}" && -n "${VALIDATION_REGISTRY_ADDRESS}" ]]; then
  if [[ "${NETWORK}" == "base-sepolia" && "${CHAIN_ID}" == "84532" && "${VALIDATION_REGISTRY_ADDRESS,,}" == "0x8004b663056a597dffe9eccc1965a193b7388713" ]]; then
    VALIDATION_BRIDGE_SOURCE="erc8004-official"
  else
    VALIDATION_BRIDGE_SOURCE="project-local-custom"
  fi
fi

DEPLOYER_PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY:-}"
ARBITER="${PROOF_OF_AUDIT_ARBITER:-}"
TREASURY_ADDRESS="${PROOF_OF_AUDIT_TREASURY_ADDRESS:-${ARBITER}}"
REQUIRED_STAKE_WEI="${PROOF_OF_AUDIT_REQUIRED_STAKE_WEI:-10000000000000000}"
REQUIRED_CHALLENGE_BOND_WEI="${PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI:-5000000000000000}"
CHALLENGE_WINDOW_SECONDS="${PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS:-86400}"
PROTOCOL_FEE_BPS="${PROOF_OF_AUDIT_PROTOCOL_FEE_BPS:-0}"
RESOLUTION_FEE_BPS="${PROOF_OF_AUDIT_RESOLUTION_FEE_BPS:-0}"

: "${RPC_URL:?PROOF_OF_AUDIT_DEPLOY_RPC_URL or BASE_SEPOLIA_RPC_URL must be set}"
: "${DEPLOYER_PRIVATE_KEY:?DEPLOYER_PRIVATE_KEY must be set}"
: "${ARBITER:?PROOF_OF_AUDIT_ARBITER must be set}"

BROADCAST_FILE="${CONTRACTS_DIR}/broadcast/DeployProofOfAudit.s.sol/${CHAIN_ID}/run-latest.json"
CONSTRUCTOR_ARGS_JSON="$(
  printf '{"arbiter":"%s","treasury":"%s","required_stake_wei":"%s","required_challenge_bond_wei":"%s","challenge_window_seconds":%s,"protocol_fee_bps":%s,"resolution_fee_bps":%s}' \
    "${ARBITER}" \
    "${TREASURY_ADDRESS}" \
    "${REQUIRED_STAKE_WEI}" \
    "${REQUIRED_CHALLENGE_BOND_WEI}" \
    "${CHALLENGE_WINDOW_SECONDS}" \
    "${PROTOCOL_FEE_BPS}" \
    "${RESOLUTION_FEE_BPS}"
)"
CONSTRUCTOR_ARGS_HEX="$(
  cast abi-encode "constructor(address,address,uint256,uint256,uint256,uint256,uint256)" \
    "${ARBITER}" \
    "${TREASURY_ADDRESS}" \
    "${REQUIRED_STAKE_WEI}" \
    "${REQUIRED_CHALLENGE_BOND_WEI}" \
    "${CHALLENGE_WINDOW_SECONDS}" \
    "${PROTOCOL_FEE_BPS}" \
    "${RESOLUTION_FEE_BPS}"
)"

cd "${CONTRACTS_DIR}"

PROOF_OF_AUDIT_ARBITER="${ARBITER}" \
PROOF_OF_AUDIT_TREASURY_ADDRESS="${TREASURY_ADDRESS}" \
PROOF_OF_AUDIT_REQUIRED_STAKE_WEI="${REQUIRED_STAKE_WEI}" \
PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI="${REQUIRED_CHALLENGE_BOND_WEI}" \
PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS="${CHALLENGE_WINDOW_SECONDS}" \
PROOF_OF_AUDIT_PROTOCOL_FEE_BPS="${PROTOCOL_FEE_BPS}" \
PROOF_OF_AUDIT_RESOLUTION_FEE_BPS="${RESOLUTION_FEE_BPS}" \
forge script script/DeployProofOfAudit.s.sol:DeployProofOfAudit \
  --rpc-url "${RPC_URL}" \
  --private-key "${DEPLOYER_PRIVATE_KEY}" \
  --broadcast

read -r CONTRACT_ADDRESS DEPLOYMENT_TX_HASH DEPLOYMENT_BLOCK_NUMBER DEPLOYER_ADDRESS < <(
  "${PYTHON_BIN}" - "${BROADCAST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
for tx, receipt in zip(payload.get("transactions", []), payload.get("receipts", [])):
    if tx.get("transactionType") == "CREATE" and tx.get("contractName") == "ProofOfAudit":
        print(
            tx.get("contractAddress") or "",
            tx.get("hash") or "",
            str(int(receipt.get("blockNumber", "0x0"), 16)),
            tx.get("transaction", {}).get("from") or "",
        )
        raise SystemExit(0)
raise SystemExit("Could not find deployed ProofOfAudit address in broadcast output")
PY
)

cast code "${CONTRACT_ADDRESS}" --rpc-url "${RPC_URL}" >/dev/null

cd "${ROOT_DIR}"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/write-release-manifest.py" \
  --manifest-file "${MANIFEST_FILE}" \
  --contract-name "ProofOfAudit" \
  --network "${NETWORK}" \
  --chain-id "${CHAIN_ID}" \
  --address "${CONTRACT_ADDRESS}" \
  --status "deployed" \
  --arbiter "${ARBITER}" \
  --treasury-address "${TREASURY_ADDRESS}" \
  --rpc-url "${RPC_URL}" \
  --explorer-base-url "${EXPLORER_BASE_URL}" \
  --required-stake-wei "${REQUIRED_STAKE_WEI}" \
  --required-challenge-bond-wei "${REQUIRED_CHALLENGE_BOND_WEI}" \
  --challenge-window-seconds "${CHALLENGE_WINDOW_SECONDS}" \
  --protocol-fee-bps "${PROTOCOL_FEE_BPS}" \
  --resolution-fee-bps "${RESOLUTION_FEE_BPS}" \
  --deployment-tx-hash "${DEPLOYMENT_TX_HASH}" \
  --deployment-block-number "${DEPLOYMENT_BLOCK_NUMBER}" \
  --deployer-address "${DEPLOYER_ADDRESS}" \
  --constructor-args-json "${CONSTRUCTOR_ARGS_JSON}" \
  --constructor-args-hex "${CONSTRUCTOR_ARGS_HEX}" \
  --verification-status "not_requested" \
  --verification-provider "basescan" \
  --registration-document-uri "${AUDITOR_REGISTRATION_URI}" \
  --registration-document-file "${AUDITOR_PUBLISHED_REGISTRATION_FILE}" \
  --registration-source-manifest "${AUDITOR_MANIFEST_FILE}" \
  --validation-bridge-registry-address "${VALIDATION_REGISTRY_ADDRESS}" \
  --validation-bridge-source "${VALIDATION_BRIDGE_SOURCE}" \
  --notes "Deployed via scripts/deploy-release.sh"

REGISTRATION_SCRIPT_ARGS=(
  "${ROOT_DIR}/scripts/write-published-registration.py"
  --manifest-file "${AUDITOR_MANIFEST_FILE}"
  --deployment-manifest-file "${MANIFEST_FILE}"
  --output-file "${AUDITOR_PUBLISHED_REGISTRATION_FILE}"
  --registration-uri "${AUDITOR_REGISTRATION_URI}"
  --public-web-url "${AUDITOR_PUBLIC_WEB_URL}"
)

if [[ -n "${AUDITOR_PUBLIC_API_URL}" ]]; then
  REGISTRATION_SCRIPT_ARGS+=(--public-api-base-url "${AUDITOR_PUBLIC_API_URL}")
fi

if [[ -n "${AUDITOR_AGENT_ID}" && -n "${AUDITOR_AGENT_REGISTRY}" ]]; then
  REGISTRATION_SCRIPT_ARGS+=(--agent-id "${AUDITOR_AGENT_ID}" --agent-registry "${AUDITOR_AGENT_REGISTRY}")
fi

"${PYTHON_BIN}" "${REGISTRATION_SCRIPT_ARGS[@]}"

echo
echo "Release deployment complete."
echo "Network: ${NETWORK} (chain ${CHAIN_ID})"
echo "Contract: ProofOfAudit"
echo "Address: ${CONTRACT_ADDRESS}"
echo "Deployment tx: ${DEPLOYMENT_TX_HASH}"
echo "Manifest: ${MANIFEST_FILE}"
echo "Registration document: ${AUDITOR_PUBLISHED_REGISTRATION_FILE}"
echo "Registration URI: ${AUDITOR_REGISTRATION_URI}"

if [[ "${DEPLOY_VERIFY}" == "1" ]]; then
  "${ROOT_DIR}/scripts/verify-release.sh"
fi
