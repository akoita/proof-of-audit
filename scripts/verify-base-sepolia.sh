#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PROOF_OF_AUDIT_DEPLOY_NETWORK="${PROOF_OF_AUDIT_DEPLOY_NETWORK:-base-sepolia}"
export PROOF_OF_AUDIT_DEPLOY_CHAIN_ID="${PROOF_OF_AUDIT_DEPLOY_CHAIN_ID:-84532}"
export PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE="${PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE:-${SCRIPT_DIR}/../deployments/base-sepolia.json}"

exec "${SCRIPT_DIR}/verify-release.sh"
