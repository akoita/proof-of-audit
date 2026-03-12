#!/usr/bin/env bash

set -euo pipefail

: "${ANVIL_HOST:=127.0.0.1}"
: "${ANVIL_PORT:=8545}"
: "${ANVIL_CHAIN_ID:=31337}"

exec anvil \
  --host "${ANVIL_HOST}" \
  --port "${ANVIL_PORT}" \
  --chain-id "${ANVIL_CHAIN_ID}"

