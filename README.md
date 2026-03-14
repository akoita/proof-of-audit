# Proof-of-Audit

[![CI](https://github.com/akoita/proof-of-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/akoita/proof-of-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
![Status: Prototype](https://img.shields.io/badge/status-prototype-orange)

Proof-of-Audit is a monorepo for an agent that audits smart contracts, publishes a staked attestation on-chain, and can be challenged with deterministic evidence.

## Overview

Proof-of-Audit combines a deterministic audit worker, a lightweight API, a web client, and an on-chain settlement contract to demonstrate how software agents can make review claims with economic accountability.

The current implementation focuses on:

- benchmark-driven smart contract audit reports
- normalized submissions for demo fixtures, deployed addresses, and source bundles
- real publish transactions and challenge flows backed by a stake
- deterministic challenge verification for curated fixture PoCs
- a browser-based demo path for submit, publish, review, and explorer-linked chain state
- a compact Foundry contract with tested stake accounting

## Status

This repository is an early-stage prototype intended for rapid iteration. The current codebase is designed for local development and demos, with a clear path toward stronger chain integration, verification, and operational hardening.

## What is in this repo

- `contracts/`: Foundry contract for publishing audits, opening challenges, and resolving stake payouts.
- `agent/`: Python audit worker with deterministic outputs for benchmark contracts.
- `api/`: FastAPI service for submit, view, publish, and challenge flows.
- `web/`: Minimal Next.js app scaffold for the demo UI.
- `demo/`: Sample contracts that map to benchmark audit outputs.

## Current scope

This repo implements a compact, coherent v1:

- one auditor identity
- one on-chain stake amount
- one challenge type
- one HTTP API flow
- one frontend path

## Quick start

### Run locally

```bash
# 0. Start the local chain
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/start-anvil.sh

# 1. Deploy the ProofOfAudit contract to Anvil and sync local app config
./scripts/deploy-local.sh

# 2. Deploy the local demo fixtures and write the fixture manifest
./scripts/deploy-demo-fixtures.sh

# 3. Start the API (loads api/.env.local automatically)
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m proof_of_audit_api.app

# 4. Start the frontend in a separate terminal (loads web/.env.local automatically)
cd /home/koita/dev/hackatons/proof-of-audit/web
pnpm dev
```

Note: `./scripts/deploy-local.sh` deploys only the `ProofOfAudit` smart contract to the local Anvil chain, then writes ignored local config for dependent components:

- `deployments/localhost.json`
- `api/.env.local`
- `web/.env.local`

If the current localhost manifest still points to a valid `ProofOfAudit` deployment on the same RPC, chain, network, and contract config, rerunning `./scripts/deploy-local.sh` now reuses that deployment and refreshes the generated config instead of creating a new address. Use `LOCAL_DEPLOYMENT_FORCE_REDEPLOY=1 ./scripts/deploy-local.sh` when you intentionally want a fresh local contract.

For localhost only, the generated `api/.env.local` also includes the Anvil publisher and arbiter keys so `POST /audits/:id/publish`, `POST /audits/:id/challenge`, and deterministic auto-resolution can submit real local transactions without extra manual exports.

It does not start Anvil, the API, or the frontend, and it does not deploy backend or web services anywhere.

Note: `./scripts/deploy-demo-fixtures.sh` deploys the local benchmark contracts to Anvil, writes `deployments/demo-fixtures.localhost.json`, and updates `api/.env.local` so the API can expose those live fixture addresses and suggested challenge PoC URIs to the web app.

### Contracts

```bash
cd /home/koita/dev/hackatons/proof-of-audit/contracts
forge test
```

### Python tests

```bash
cd /home/koita/dev/hackatons/proof-of-audit
python3 -m pip install setuptools wheel
python3 -m pip install --no-build-isolation -e '.[dev]'
make test-python
```

The Python suite runs with `pytest`, configured via `pyproject.toml`.

### Run the API

```bash
cd /home/koita/dev/hackatons/proof-of-audit
python3 -m pip install setuptools wheel
python3 -m pip install --no-build-isolation -e '.[dev]'
PYTHONPATH=agent:api python3 -m proof_of_audit_api.app
```

Server defaults:

- `http://127.0.0.1:8080`
- data persisted under `api/data/`
- interactive API docs at `http://127.0.0.1:8080/docs`

### Run the web app

```bash
cd /home/koita/dev/hackatons/proof-of-audit/web
pnpm install
NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL=http://127.0.0.1:8080 pnpm dev
```

Web defaults:

- `http://127.0.0.1:3000`
- expects the API server to already be running

### Run system end-to-end tests

```bash
cd /home/koita/dev/hackatons/proof-of-audit
make test-system-e2e
```

The system e2e harness starts a dedicated Anvil instance, deploys the local contract and demo fixtures, runs the real API on an isolated port, and drives the submit, publish, challenge, and resolve lifecycle over HTTP.

### Run UI end-to-end tests

```bash
cd /home/koita/dev/hackatons/proof-of-audit/web
pnpm install
pnpm exec playwright install --with-deps chromium

cd /home/koita/dev/hackatons/proof-of-audit
make test-ui-e2e
```

The UI e2e harness starts a dedicated Anvil instance, deploys the local contract and demo fixtures, runs the API and Next.js app on isolated ports, and validates the browser flow against the real stack.

## API shape

- `GET /health`
- `GET /config`
- `GET /fixtures`
- `GET /audits`
- `POST /audits`
- `GET /audits/:id`
- `POST /audits/:id/publish`
- `POST /audits/:id/challenge`
- `POST /audits/:id/resolve`

### Example create audit request

```json
{
  "input_kind": "demo_fixture",
  "fixture_id": "vulnerable-bank",
  "submitted_by": "judge-demo"
}
```

Additional supported submission shapes:

```json
{
  "input_kind": "deployed_address",
  "chain_id": 84532,
  "contract_address": "0x1000000000000000000000000000000000000001",
  "entry_contract": "Vault",
  "submitted_by": "judge-demo"
}
```

```json
{
  "input_kind": "source_bundle",
  "source_bundle_uri": "ipfs://uploads/dual-risk-vault.zip",
  "source_bundle_label": "Dual Risk Vault upload",
  "entry_contract": "DualRiskVault",
  "submitted_by": "judge-demo"
}
```

## Demo benchmarks

- `0x1000000000000000000000000000000000000001`: reentrancy bug
- `0x1000000000000000000000000000000000000002`: missing access control
- `0x1000000000000000000000000000000000000003`: clean contract
- `0x1000000000000000000000000000000000000004`: multi-finding vault with access control and unchecked payout issues

Unknown contracts return a low-confidence informational report instead of fabricated vulnerabilities.

## Architecture

1. A user submits a demo fixture, deployed address, or source bundle through the web app or API.
2. The audit worker maps the normalized submission to a deterministic benchmark report.
3. The API persists the report and prepares on-chain publication metadata when the target is deployable.
4. The contract records the staked attestation and challenge lifecycle.
5. A challenger can submit a curated PoC artifact, the deterministic verifier evaluates it, and the contract resolves stake payouts.

### Demo challenge artifacts

- `ipfs://reentrancy-bank/withdraw-drain`: confirms the reported reentrancy finding and should reject the challenge
- `ipfs://admin-setter/unauthorized-admin-change`: confirms the reported access control finding and should reject the challenge
- `ipfs://unchecked-treasury/unchecked-call-failure`: confirms the reported unchecked call finding and should reject the challenge
- `ipfs://clean-vault/missed-reentrancy`: demonstrates a missed issue against the clean benchmark and should uphold the challenge

## Development

Core commands:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
python3 -m pip install setuptools wheel
python3 -m pip install --no-build-isolation -e '.[dev]'
make test-python
make test-system-e2e
make test-ui-e2e
make test-e2e
cd contracts && forge test
cd ../web && pnpm build
```

See the project roadmap in `docs/ROADMAP.md`.
See deployment setup in `docs/DEPLOYMENT.md`.
See submission UX guidance in `docs/SUBMISSION_UX.md`.

## Deployment status

Base Sepolia deployment settings and manifest scaffolding are included in this repository.

- manifest: `deployments/base-sepolia.json`
- deploy script: `scripts/deploy-base-sepolia.sh`
- Foundry deployment script: `contracts/script/DeployProofOfAudit.s.sol`

Current Base Sepolia deployment:

- contract: `0xf2dA3947d028b85e597Fe1Df4633a87eF4A85F24`
- deploy tx: `0xf3896f7904443a84cedc45f64cf7259be2133c6c4d84d9a21a41e6f4321e6f41`
- explorer: `https://sepolia.basescan.org/address/0xf2dA3947d028b85e597Fe1Df4633a87eF4A85F24`

Repeatable release commands:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
make deploy-base-sepolia
make verify-base-sepolia
```

## Notes

- The contract path is runnable and tested in this environment.
- The Python agent and API install from the root `pyproject.toml`.
- The web app uses a direct browser connection to the Python API, so the API exposes permissive local-demo CORS headers.

## Security

This project is a prototype and should not be treated as production-ready smart contract infrastructure. Contract logic, API flows, and challenge verification should all be reviewed before handling real value or adversarial usage.

## License

This project is licensed under the MIT License. See `LICENSE`.
