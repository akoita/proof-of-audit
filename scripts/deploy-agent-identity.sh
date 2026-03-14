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
IDENTITY_MODE="${PROOF_OF_AUDIT_ERC8004_IDENTITY_MODE:-}"
OFFICIAL_ERC8004_REGISTRY="${PROOF_OF_AUDIT_ERC8004_IDENTITY_REGISTRY:-}"

DEPLOYER_PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY:-}"

: "${RPC_URL:?PROOF_OF_AUDIT_IDENTITY_RPC_URL or PROOF_OF_AUDIT_DEPLOY_RPC_URL or BASE_SEPOLIA_RPC_URL must be set}"

if [[ -z "${IDENTITY_MODE}" ]]; then
  if [[ "${NETWORK}" == "base-sepolia" && "${CHAIN_ID}" == "84532" ]]; then
    IDENTITY_MODE="official"
  else
    IDENTITY_MODE="custom"
  fi
fi

if [[ -z "${OFFICIAL_ERC8004_REGISTRY}" && "${NETWORK}" == "base-sepolia" && "${CHAIN_ID}" == "84532" ]]; then
  OFFICIAL_ERC8004_REGISTRY="0x8004A818BFB912233c491871b3d84c89A494BD9e"
fi

DEFAULT_DEPLOYER_ADDRESS=""
if [[ -n "${DEPLOYER_PRIVATE_KEY}" ]]; then
  DEFAULT_DEPLOYER_ADDRESS="$(cast wallet address --private-key "${DEPLOYER_PRIVATE_KEY}")"
fi

AGENT_REGISTRY_ADMIN="${PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN:-${DEFAULT_DEPLOYER_ADDRESS}}"
AGENT_REGISTRY_ADMIN_PRIVATE_KEY="${PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN_PRIVATE_KEY:-${PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY:-${DEPLOYER_PRIVATE_KEY}}}"
AUDITOR_OWNER_PRIVATE_KEY="${PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY:-${PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY:-${DEPLOYER_PRIVATE_KEY}}}"
DEFAULT_AUDITOR_OWNER=""
if [[ -n "${AUDITOR_OWNER_PRIVATE_KEY}" ]]; then
  DEFAULT_AUDITOR_OWNER="$(cast wallet address --private-key "${AUDITOR_OWNER_PRIVATE_KEY}")"
fi
AUDITOR_OWNER="${PROOF_OF_AUDIT_AUDITOR_OWNER:-${PROOF_OF_AUDIT_ARBITER:-${DEFAULT_AUDITOR_OWNER:-${AGENT_REGISTRY_ADMIN:-}}}}"

: "${AUDITOR_OWNER:?PROOF_OF_AUDIT_AUDITOR_OWNER or PROOF_OF_AUDIT_ARBITER must be set}"
: "${AUDITOR_REGISTRATION_URI:?PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI must be set}"

DEPLOY_BROADCAST_FILE="${CONTRACTS_DIR}/broadcast/DeployAgentIdentityRegistry.s.sol/${CHAIN_ID}/run-latest.json"
REGISTRY_ADDRESS=""
REGISTRY_DEPLOY_TX_HASH=""
REGISTER_TX_HASH=""
AGENT_ID=""
IDENTITY_SOURCE=""

read_existing_identity() {
  "${PYTHON_BIN}" - "${MANIFEST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("", "", "", "", "", sep="\n")
    raise SystemExit(0)

payload = json.loads(path.read_text(encoding="utf-8"))
identity = payload.get("auditor_identity", {})
if not isinstance(identity, dict):
    identity = {}

print(identity.get("registry_address") or "")
print(identity.get("agent_id") or "")
print(identity.get("register_tx_hash") or "")
print(identity.get("deploy_tx_hash") or "")
print(identity.get("source") or "")
PY
}

if [[ "${IDENTITY_MODE}" == "official" ]]; then
  : "${OFFICIAL_ERC8004_REGISTRY:?PROOF_OF_AUDIT_ERC8004_IDENTITY_REGISTRY must be set for official mode}"
  : "${AUDITOR_OWNER_PRIVATE_KEY:?PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY, PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY, or DEPLOYER_PRIVATE_KEY must be set for official mode}"

  DERIVED_OWNER="$(cast wallet address --private-key "${AUDITOR_OWNER_PRIVATE_KEY}")"
  if [[ "${AUDITOR_OWNER,,}" != "${DERIVED_OWNER,,}" ]]; then
    echo "Auditor owner mismatch: expected ${AUDITOR_OWNER}, derived ${DERIVED_OWNER} from PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY" >&2
    exit 1
  fi

  REGISTRY_ADDRESS="${OFFICIAL_ERC8004_REGISTRY}"
  IDENTITY_SOURCE="erc8004-official"
  cast code "${REGISTRY_ADDRESS}" --rpc-url "${RPC_URL}" >/dev/null

  read -r EXISTING_REGISTRY EXISTING_AGENT_ID EXISTING_REGISTER_TX_HASH EXISTING_DEPLOY_TX_HASH EXISTING_SOURCE < <(read_existing_identity)

  if [[ -n "${EXISTING_AGENT_ID}" && "${EXISTING_REGISTRY,,}" == "${REGISTRY_ADDRESS,,}" ]]; then
    AGENT_ID="${EXISTING_AGENT_ID}"
    REGISTER_TX_HASH="${EXISTING_REGISTER_TX_HASH}"
    REGISTRY_DEPLOY_TX_HASH="${EXISTING_DEPLOY_TX_HASH}"
  else
    REGISTER_TX_HASH="$(
      cast send "${REGISTRY_ADDRESS}" \
        "register(string)" \
        "${AUDITOR_REGISTRATION_URI}" \
        --rpc-url "${RPC_URL}" \
        --private-key "${AUDITOR_OWNER_PRIVATE_KEY}" \
        --json \
      | "${PYTHON_BIN}" -c 'import json, sys; payload = json.load(sys.stdin); print(payload.get("transactionHash") or payload.get("txHash") or payload.get("hash") or "")'
    )"

    if [[ -z "${REGISTER_TX_HASH}" ]]; then
      echo "Could not parse official ERC-8004 register transaction hash" >&2
      exit 1
    fi

    AGENT_ID="$(
      "${PYTHON_BIN}" - "${REGISTRY_ADDRESS}" "${REGISTER_TX_HASH}" "${RPC_URL}" <<'PY'
import json
import subprocess
import sys

registry = sys.argv[1].lower()
tx_hash = sys.argv[2]
rpc_url = sys.argv[3]
topic0 = subprocess.check_output(
    ["cast", "keccak", "Registered(uint256,string,address)"],
    text=True,
).strip().lower()
receipt = json.loads(
    subprocess.check_output(
        ["cast", "receipt", tx_hash, "--rpc-url", rpc_url, "--json"],
        text=True,
    )
)
for log in receipt.get("logs", []):
    if str(log.get("address") or "").lower() != registry:
        continue
    topics = [str(topic).lower() for topic in log.get("topics", [])]
    if len(topics) < 3 or topics[0] != topic0:
        continue
    print(int(topics[1], 16))
    raise SystemExit(0)
raise SystemExit("Could not find Registered event for official ERC-8004 identity registration")
PY
    )"
  fi
elif [[ "${IDENTITY_MODE}" == "custom" ]]; then
  : "${DEPLOYER_PRIVATE_KEY:?DEPLOYER_PRIVATE_KEY must be set for custom identity mode}"
  : "${AGENT_REGISTRY_ADMIN:?PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN must be set for custom identity mode}"
  : "${AGENT_REGISTRY_ADMIN_PRIVATE_KEY:?PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN_PRIVATE_KEY, PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY, or DEPLOYER_PRIVATE_KEY must be set for custom identity mode}"

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
  IDENTITY_SOURCE="project-local-custom"
else
  echo "Unsupported PROOF_OF_AUDIT_ERC8004_IDENTITY_MODE=${IDENTITY_MODE}" >&2
  exit 1
fi

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

MANIFEST_ARGS=(
  "${ROOT_DIR}/scripts/write-release-manifest.py"
  --manifest-file "${MANIFEST_FILE}" \
  --registration-document-uri "${AUDITOR_REGISTRATION_URI}" \
  --registration-document-file "${AUDITOR_PUBLISHED_REGISTRATION_FILE}" \
  --registration-source-manifest "${AUDITOR_MANIFEST_FILE}" \
  --auditor-identity-registry-address "${REGISTRY_ADDRESS}" \
  --auditor-identity-agent-id "${AGENT_ID}" \
  --auditor-identity-source "${IDENTITY_SOURCE}" \
  --auditor-identity-owner "${AUDITOR_OWNER}" \
  --auditor-identity-registration-uri "${AUDITOR_REGISTRATION_URI}"
)

if [[ -n "${AGENT_REGISTRY_ADMIN:-}" && "${IDENTITY_MODE}" == "custom" ]]; then
  MANIFEST_ARGS+=(--auditor-identity-admin "${AGENT_REGISTRY_ADMIN}")
else
  MANIFEST_ARGS+=(--auditor-identity-admin "")
fi
if [[ -n "${REGISTRY_DEPLOY_TX_HASH}" ]]; then
  MANIFEST_ARGS+=(--auditor-identity-deploy-tx-hash "${REGISTRY_DEPLOY_TX_HASH}")
else
  MANIFEST_ARGS+=(--auditor-identity-deploy-tx-hash "")
fi
if [[ -n "${REGISTER_TX_HASH}" ]]; then
  MANIFEST_ARGS+=(--auditor-identity-register-tx-hash "${REGISTER_TX_HASH}")
else
  MANIFEST_ARGS+=(--auditor-identity-register-tx-hash "")
fi

"${PYTHON_BIN}" "${MANIFEST_ARGS[@]}"

echo
echo "Auditor identity registration complete."
echo "Mode: ${IDENTITY_MODE}"
echo "Network: ${NETWORK} (chain ${CHAIN_ID})"
echo "Registry: ${REGISTRY_ADDRESS}"
echo "Agent ID: ${AGENT_ID}"
echo "Owner: ${AUDITOR_OWNER}"
echo "Registration URI: ${AUDITOR_REGISTRATION_URI}"
echo "Manifest: ${MANIFEST_FILE}"
