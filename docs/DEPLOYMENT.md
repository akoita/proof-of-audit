# Deployment

## Localhost with Anvil

The fastest local development loop is:

1. start Anvil
2. deploy `ProofOfAudit` to localhost
3. deploy the demo fixtures to localhost
4. let the deployment scripts write fresh local config for the API and web app
5. run the API and frontend against those generated values

### Condensed local flow

```bash
# 0. Start the local chain
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/start-anvil.sh

# 1. Deploy the ProofOfAudit contract to Anvil and sync local app config
./scripts/deploy-local.sh

# 2. Deploy the demo fixtures and write the local fixture manifest
./scripts/deploy-demo-fixtures.sh

# 3. Start the API (loads api/.env.local automatically)
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m proof_of_audit_api.app

# 4. Start the frontend in a separate terminal (loads web/.env.local automatically)
cd /home/koita/dev/hackatons/proof-of-audit/web
pnpm dev
```

### Start Anvil

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/start-anvil.sh
```

Defaults:

- RPC URL: `http://127.0.0.1:8545`
- chain id: `31337`
- deployer key: first default Anvil key, unless overridden
- arbiter: first default Anvil account, unless overridden

### Deploy locally and sync config

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/deploy-local.sh
```

This script:

- deploys the `ProofOfAudit` smart contract to the running local Anvil chain
- verifies that bytecode exists at the deployed address
- writes `deployments/localhost.json`
- writes `api/.env.local`
- writes `web/.env.local`
- includes the localhost publisher and arbiter private keys in `api/.env.local` so the API can submit real local publish, challenge, and resolve transactions

If `deployments/localhost.json` already points to a live `ProofOfAudit` contract on the same RPC, chain id, network, and constructor config, the script reuses that deployment and only refreshes the generated config files. Set `LOCAL_DEPLOYMENT_FORCE_REDEPLOY=1` to bypass reuse and deploy a fresh contract address on the same chain.

Generated files are ignored by Git and are meant for local development only.

This script does not:

- start Anvil
- start the API server
- start the frontend dev server
- deploy backend or frontend services

It only handles the on-chain localhost deployment plus local config synchronization for the dependent app components.

### Deploy local demo fixtures

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/deploy-demo-fixtures.sh
```

This script:

- deploys the demo fixture contracts to the running local Anvil chain
- verifies that bytecode exists at the deployed addresses
- writes `deployments/demo-fixtures.localhost.json`
- updates `api/.env.local` with `PROOF_OF_AUDIT_DEMO_FIXTURES_FILE`
- includes the suggested deterministic challenge proof URI for each fixture in the generated manifest

This script does not:

- start Anvil
- start the API server
- start the frontend dev server
- deploy backend or frontend services

It only handles local demo fixture deployment and fixture manifest synchronization.

### Run the API against the generated local config

```bash
cd /home/koita/dev/hackatons/proof-of-audit
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m proof_of_audit_api.app
```

The API automatically loads `api/.env.local` if it exists.

### Run the frontend against the generated local config

```bash
cd /home/koita/dev/hackatons/proof-of-audit/web
pnpm dev
```

Next.js automatically loads `web/.env.local`.

### Local deterministic challenge proofs

The demo fixtures ship with curated PoC URIs that the API verifier knows how to evaluate deterministically:

- `ipfs://reentrancy-bank/withdraw-drain`
- `ipfs://admin-setter/unauthorized-admin-change`
- `ipfs://unchecked-treasury/unchecked-call-failure`
- `ipfs://clean-vault/missed-reentrancy`

If the submitted PoC matches the curated fixture artifact, the API records a verifier outcome and, when the local arbiter key is configured, resolves the on-chain challenge immediately.

### Local overrides

You can override defaults without committing secrets:

```bash
export ANVIL_RPC_URL=http://127.0.0.1:8545
export PROOF_OF_AUDIT_ARBITER=0xYourLocalArbiter
export LOCAL_DEPLOYER_PRIVATE_KEY=0xYourLocalPrivateKey
./scripts/deploy-local.sh
```

## Base Sepolia

Proof-of-Audit is configured to deploy to Base Sepolia with the following defaults:

- network: `base-sepolia`
- chain id: `84532`
- required stake: `0.01 ETH`
- required challenge bond: `0.005 ETH`
- challenge window: `86400` seconds

The deployment manifest lives in `deployments/base-sepolia.json`.

### Repeatable release flow

The release path is now split into two explicit scripts:

1. `./scripts/deploy-base-sepolia.sh`
2. `./scripts/verify-base-sepolia.sh`
3. `./scripts/deploy-base-sepolia-identity.sh`

The deploy script:

- broadcasts the Foundry deployment
- parses the Foundry broadcast output
- records the deployed address, tx hash, block number, deployer, and encoded constructor args in `deployments/base-sepolia.json`
- regenerates the published auditor registration document at `docs/registrations/proof-of-audit-auditor.json`
- records the canonical registration URI and source manifest in the deployment manifest
- can optionally chain into verification when `PROOF_OF_AUDIT_DEPLOY_VERIFY=1`

The verify script:

- reads the recorded deployment manifest
- reuses the recorded encoded constructor args
- runs `forge verify-contract`
- writes verification status back into the manifest when verification succeeds

The identity deploy script:

- registers the auditor against the published registration document URI
- uses the official ERC-8004 Base Sepolia `IdentityRegistry` by default on Base Sepolia
- keeps the project-local `AgentIdentityRegistry` path for localhost and other fallback environments
- rewrites `docs/registrations/proof-of-audit-auditor.json` with the on-chain registration reference
- records the registry address, agent id, owner, and tx hashes in `deployments/base-sepolia.json`

The validation bridge path:

- uses the official ERC-8004 Base Sepolia `ValidationRegistry` by default on Base Sepolia
- records the canonical validation registry metadata in `deployments/base-sepolia.json`
- keeps the native `ProofOfAudit` contract as the settlement source of truth

### Regenerate the published registration document without redeploying

```bash
cd /home/koita/dev/hackatons/proof-of-audit
python3 scripts/write-published-registration.py \
  --manifest-file agent/proof_of_audit_agent/auditor_manifest.json \
  --deployment-manifest-file deployments/base-sepolia.json \
  --output-file docs/registrations/proof-of-audit-auditor.json \
  --registration-uri https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json \
  --public-web-url https://github.com/akoita/proof-of-audit
```

Add `--public-api-base-url` once the API has a stable public host, and add `--agent-id` plus `--agent-registry` once on-chain identity registration is available.

## Required environment variables

Copy `.env.example` into your preferred local secret-loading workflow and set:

- `BASE_SEPOLIA_RPC_URL`
- `BASESCAN_API_KEY`
- `DEPLOYER_PRIVATE_KEY`
- `PROOF_OF_AUDIT_ARBITER`

Registration publication defaults can also be overridden:

- `PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL`
- `PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL`
- `PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI`
- `PROOF_OF_AUDIT_AUDITOR_PUBLISHED_REGISTRATION_FILE`
- `PROOF_OF_AUDIT_AUDITOR_AGENT_ID`
- `PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY`
- `PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY`
- `PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN`
- `PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN_PRIVATE_KEY`
- `PROOF_OF_AUDIT_AUDITOR_OWNER`
- `PROOF_OF_AUDIT_ERC8004_IDENTITY_MODE`
- `PROOF_OF_AUDIT_ERC8004_IDENTITY_REGISTRY`
- `PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS`
- `PROOF_OF_AUDIT_VALIDATION_BRIDGE_SOURCE`
- `PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY`
- `PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY`
- `PROOF_OF_AUDIT_VALIDATOR_ADDRESS`
- `PROOF_OF_AUDIT_RUNTIME_API_URL`

The API can target the deployed contract with:

- `PROOF_OF_AUDIT_CONTRACT_ADDRESS`
- `PROOF_OF_AUDIT_RPC_URL`
- `PROOF_OF_AUDIT_PRIVATE_KEY`
- `PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY`

## Dry run

```bash
cd /home/koita/dev/hackatons/proof-of-audit/contracts
forge script script/DeployProofOfAudit.s.sol:DeployProofOfAudit --rpc-url base_sepolia
```

## Live deploy

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/deploy-base-sepolia.sh
```

### Verify an existing deployment

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/verify-base-sepolia.sh
```

### Optional one-command deploy + verify

```bash
cd /home/koita/dev/hackatons/proof-of-audit
PROOF_OF_AUDIT_DEPLOY_VERIFY=1 ./scripts/deploy-base-sepolia.sh
```

### Deploy the on-chain auditor identity

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/deploy-base-sepolia-identity.sh
```

On Base Sepolia this script now targets the official ERC-8004 `IdentityRegistry` at `0x8004A818BFB912233c491871b3d84c89A494BD9e` unless you explicitly override `PROOF_OF_AUDIT_ERC8004_IDENTITY_REGISTRY`.

The registration transaction must be signed by the wallet that should own the auditor identity NFT, so set `PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY` when the auditor owner is not the same as the deployer.

### Release manifest fields

After a successful deploy, `deployments/base-sepolia.json` records:

- contract address
- deployment tx hash
- deployment block number
- deployer address
- constructor args as named fields
- constructor args as encoded hex for verification reuse
- verification status and provider metadata
- registration document URI, source manifest, and generated file path
- on-chain auditor identity registry address and agent id
- identity source metadata so the repo can distinguish the official ERC-8004 path from the project-local fallback
- validation bridge registry address and source metadata

### Rollback and redeploy basics

There is no proxy or upgrade path in v1, so rollback means operational rollback, not contract mutation.

If a release is bad:

1. stop pointing the API or frontend at the bad address
2. deploy a fresh contract with corrected parameters or code
3. update the manifest and downstream runtime config to the new address
4. re-run verification for the new address

If you need to redeploy with the same bytecode but different constructor inputs:

1. export the new env vars
2. run `./scripts/deploy-base-sepolia.sh`
3. verify with `./scripts/verify-base-sepolia.sh`
4. update any app runtime env using the newly recorded manifest values

## Current status

Live Base Sepolia deployment:

- contract: `0xf2dA3947d028b85e597Fe1Df4633a87eF4A85F24`
- deploy tx: `0xf3896f7904443a84cedc45f64cf7259be2133c6c4d84d9a21a41e6f4321e6f41`
- arbiter: `0x9Ed13E9b9FC135D35CE78C35866412dB08897E29`
- explorer: `https://sepolia.basescan.org/address/0xf2dA3947d028b85e597Fe1Df4633a87eF4A85F24`
- canonical ERC-8004 Base Sepolia identity registry: `0x8004A818BFB912233c491871b3d84c89A494BD9e`
- canonical ERC-8004 Base Sepolia validation registry: `0x8004B663056A597Dffe9eCcC1965A193B7388713`
- auditor agent id: see `deployments/base-sepolia.json`

Verification has been recorded in `deployments/base-sepolia.json` and the contract is verified on BaseScan.
