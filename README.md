# Proof-of-Audit

[![CI](https://github.com/akoita/proof-of-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/akoita/proof-of-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
![Status: Prototype](https://img.shields.io/badge/status-prototype-orange)

Proof-of-Audit is a monorepo for an agent that audits smart contracts, publishes a staked attestation on-chain, and can be challenged with deterministic evidence.

## Overview

Proof-of-Audit combines a deterministic audit worker, a lightweight API, a web client, and an on-chain settlement contract to demonstrate how software agents can make review claims with economic accountability.

The current implementation focuses on:

- benchmark-driven smart contract audit reports
- publish and challenge flows backed by a stake
- a browser-based demo path for submit, publish, and review
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

### Contracts

```bash
cd /home/koita/dev/hackatons/proof-of-audit/contracts
forge test
```

### Python tests

```bash
cd /home/koita/dev/hackatons/proof-of-audit
python3 -m pip install -r api/requirements.txt
make test-python
```

### Run the API

```bash
cd /home/koita/dev/hackatons/proof-of-audit
python3 -m pip install -r api/requirements.txt
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

## API shape

- `GET /health`
- `GET /config`
- `GET /audits`
- `POST /audits`
- `GET /audits/:id`
- `POST /audits/:id/publish`
- `POST /audits/:id/challenge`

### Example create audit request

```json
{
  "contract_address": "0x1000000000000000000000000000000000000001",
  "submitted_by": "judge-demo"
}
```

## Demo benchmarks

- `0x1000000000000000000000000000000000000001`: reentrancy bug
- `0x1000000000000000000000000000000000000002`: missing access control
- `0x1000000000000000000000000000000000000003`: clean contract

Unknown contracts return a low-confidence informational report instead of fabricated vulnerabilities.

## Architecture

1. A user submits a target contract address through the web app or API.
2. The audit worker maps the address to a deterministic benchmark report.
3. The API persists the report and prepares on-chain publication metadata.
4. The contract records the staked attestation and challenge lifecycle.
5. A challenger can submit evidence, and the contract resolves stake payouts.

## Development

Core commands:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
python3 -m pip install -r api/requirements.txt
make test-python
cd contracts && forge test
cd ../web && pnpm build
```

See the project roadmap in `docs/ROADMAP.md`.
See deployment setup in `docs/DEPLOYMENT.md`.

## Deployment status

Base Sepolia deployment settings and manifest scaffolding are included in this repository.

- manifest: `deployments/base-sepolia.json`
- deploy script: `scripts/deploy-base-sepolia.sh`
- Foundry deployment script: `contracts/script/DeployProofOfAudit.s.sol`

The live contract address is still pending until a funded deployer and RPC credentials are available.

## Notes

- The contract path is runnable and tested in this environment.
- The Python agent uses the system Python, and the API dependencies are listed in `api/requirements.txt`.
- The web app uses a direct browser connection to the Python API, so the API exposes permissive local-demo CORS headers.

## Security

This project is a prototype and should not be treated as production-ready smart contract infrastructure. Contract logic, API flows, and challenge verification should all be reviewed before handling real value or adversarial usage.

## License

This project is licensed under the MIT License. See `LICENSE`.
