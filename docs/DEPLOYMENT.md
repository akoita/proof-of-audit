# Deployment

## Localhost with Anvil

The fastest local development loop is:

1. start Anvil
2. deploy `ProofOfAudit` to localhost
3. deploy the demo fixtures to localhost
4. let the deployment scripts write fresh local config for the API and web app
5. run the API and frontend against those generated values

The automated E2E and system-E2E stack scripts now generate their own isolated env files under `.tmp/...` and no longer overwrite `api/.env.local` or `web/.env.local`. Local dev config remains owned by the explicit localhost deployment flow below.

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
- challenge resolution window: `172800` seconds

The deployment manifest lives in `deployments/base-sepolia.json`.

### Immutable deployment parameters

The `ProofOfAudit` constructor validates its parameters at deploy time and reverts on
invalid input: the arbiter, required stake, required challenge bond, challenge window, and
challenge resolution window must all be non-zero, the treasury must be non-zero, and both
fee rates must be `<= 100%`. The challenge resolution window bounds how long a challenged
request claim may wait for arbiter resolution before anyone can neutrally expire the
challenge and unfreeze settlement (`PROOF_OF_AUDIT_CHALLENGE_RESOLUTION_WINDOW_SECONDS`,
default `172800`).
All constructor parameters are immutable — there is no upgrade, pause, or recovery path.
In particular, the arbiter is the sole dispute resolver: if the arbiter key is lost or
unusable, the escrow (stake + bond) of any challenged audit is permanently locked. Protect
the arbiter key accordingly.

For the external `agent-forge` architecture, use
[AGENT_FORGE_OPERATIONS.md](./AGENT_FORGE_OPERATIONS.md) as the primary runbook
for service topology, staging-storage requirements, local dev against a hosted
service, and failure/debugging workflow.

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

### Deploy reusable Base Sepolia vulnerable targets

If you want stable contracts for smoke tests, screenshots, or repeated manual test runs, deploy the
fixture suite to Base Sepolia and commit the resulting manifest instead of exposing them as public
workbench fixtures.

```bash
cd /home/koita/dev/hackatons/proof-of-audit
PROOF_OF_AUDIT_FIXTURE_RPC_URL="$BASE_SEPOLIA_RPC_URL" \
PROOF_OF_AUDIT_FIXTURE_PRIVATE_KEY="$DEPLOYER_PRIVATE_KEY" \
BASESCAN_API_KEY="$BASESCAN_API_KEY" \
./scripts/deploy-base-sepolia-fixtures.sh
```

This script:

- deploys the contracts defined in `demo/fixtures.catalog.json` to the configured Base Sepolia RPC
- verifies that bytecode exists at each deployed address
- attempts contract source verification on Sourcify and BaseScan for each fixture
- writes `deployments/demo-fixtures.base-sepolia.json`
- records reusable deployment metadata per target, including address, tx hash, block number, deployer, explorer URL, and per-provider verification status
- does **not** update `api/.env.local` or enable these contracts as public UI fixtures

Verification behavior:

- Sourcify verification is attempted by default and does not require an API key.
- BaseScan verification is attempted by default when `PROOF_OF_AUDIT_FIXTURE_VERIFY_API_KEY`,
  `PROOF_OF_AUDIT_VERIFY_API_KEY`, or `BASESCAN_API_KEY` is set.
- The script exits non-zero if any fixture ends without a verified source provider unless
  `PROOF_OF_AUDIT_FIXTURE_ALLOW_UNVERIFIED=1` is set.

The intended workflow is:

1. deploy the reusable targets with `./scripts/deploy-base-sepolia-fixtures.sh`
2. inspect the manifest and explorer links
3. commit `deployments/demo-fixtures.base-sepolia.json`
4. use those addresses via `deployed_address` submissions in the testnet workbench or smoke tests

This keeps the public testnet UX focused on real target submissions while still giving operators a
stable, committed set of known vulnerable contracts for repeatable validation.

See [TESTNET_FIXTURES.md](./TESTNET_FIXTURES.md) for the manifest shape and usage guidance.

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

### Key roles and separation

The challenge game depends on four trust roles being **distinct signing
addresses**. The party staking behind published verdicts must not also be the
party resolving disputes or writing reputation, otherwise the economic checks
collapse.

| Role | Env var | Purpose |
| --- | --- | --- |
| Publisher | `PROOF_OF_AUDIT_PRIVATE_KEY` | Signs and stakes behind published audit verdicts. |
| Arbiter | `PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY` | Resolves challenges / disputes. |
| Validator | `PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY` | Signs ERC-8004 validation-registry attestations. |
| Reputation operator | `PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY` | Records reputation claims and resolutions. |

On any **non-local** network these four must resolve to different addresses. If
any two of them share an address (for example because a role key is unset and
falls back through the env cascade to `PROOF_OF_AUDIT_PRIVATE_KEY`), the API
**refuses to start** and reports which roles collide and which env vars to set.

On **local** development networks (network names containing `anvil`,
`localhost`, `eth-tester`, or equal to `local`/`tester`, including the
`anvil-system-e2e` stack) a single shared key is tolerated: the API logs one
prominent warning and continues. Single-key mode is acceptable only for local
development.

`PROOF_OF_AUDIT_CHALLENGER_PRIVATE_KEY` and
`PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY` are convenience signers and are
**not** part of the separation requirement; they may share an address with any
trust role.

## API container image

The repository now includes a deployable API image definition at `api/Dockerfile`.

Build the Cloud Run-ready image from the repository root so the Docker build can include the Python packages, deployment metadata, registration document, and generated contract ABI artifact:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
docker build -f api/Dockerfile -t proof-of-audit-api .
```

Run it locally with the API bound to `0.0.0.0:8080`:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
docker run --rm -p 8080:8080 proof-of-audit-api
```

## Cloud SQL PostgreSQL

The API now supports `PROOF_OF_AUDIT_STORE_KIND=cloudsql-postgres` for deployed persistence.

Runtime contract:

- `PROOF_OF_AUDIT_STORE_KIND=cloudsql-postgres`
- `PROOF_OF_AUDIT_STORE_PATH` is only used by the `json` and `sqlite` stores and is ignored for Cloud SQL PostgreSQL
- `PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME` must be the Cloud SQL instance connection name in `project:region:instance` form
- `PROOF_OF_AUDIT_STORE_DATABASE` must be the PostgreSQL database name
- `PROOF_OF_AUDIT_STORE_USER` must be the PostgreSQL user name
- `PROOF_OF_AUDIT_STORE_PASSWORD` is required when `PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH=false`
- `PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH=true` enables automatic IAM database authentication through the Cloud SQL Python connector
- `PROOF_OF_AUDIT_STORE_IP_TYPE` may be `public`, `private`, or `psc`

Recommended Cloud Run configuration for the production path:

- attach the Cloud SQL instance to the Cloud Run service
- grant the runtime service account the `Cloud SQL Client` role
- enable automatic IAM database authentication with `PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH=true`
- use the IAM principal name as `PROOF_OF_AUDIT_STORE_USER`
- if `PROOF_OF_AUDIT_STORE_IP_TYPE=private` or `psc`, configure Cloud Run egress so the service can reach the same VPC path as the database
- keep `PROOF_OF_AUDIT_STORE_PATH` unset for this mode

Example runtime env for Cloud Run:

```bash
PROOF_OF_AUDIT_STORE_KIND=cloudsql-postgres
PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME=my-project:europe-west1:proof-of-audit
PROOF_OF_AUDIT_STORE_DATABASE=proof_of_audit
PROOF_OF_AUDIT_STORE_USER=proof-of-audit-api@my-project.iam
PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH=true
PROOF_OF_AUDIT_STORE_IP_TYPE=private
```

Local development and automated tests should continue to use `PROOF_OF_AUDIT_STORE_KIND=sqlite`.

For publish, challenge, and resolve transactions, pass the same runtime env vars documented above into the container (for example with `--env-file` or explicit `-e` flags). The image bakes in the repo's default deployment metadata and registration document, and it keeps writable audit state under `/app/api/data`.

Recommended Artifact Registry image name:

- `proof-of-audit-api`

This image is intended to receive environment tags such as `testnet-candidate` and `mainnet-release` in the release workflow.

## Web container image

The repository now includes a Cloud Run-ready Next.js image definition at `web/Dockerfile`.

The web app builds with Next.js standalone output so the runtime image only needs the compiled server bundle, static assets, and public files.

Build the image from the repository root:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
docker build \
  -f web/Dockerfile \
  -t proof-of-audit-web .
```

At runtime, set `PROOF_OF_AUDIT_API_URL` on the Cloud Run service. The Next.js server exposes that value to the browser through a runtime config endpoint, so the same image can be reused across environments without rebuilding. The legacy `NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL` runtime env is still accepted as a fallback for compatibility.

Run it locally on port `3000` mapped to the container's Cloud Run port `8080`:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
docker run --rm -p 3000:8080 \
  -e PROOF_OF_AUDIT_API_URL=http://127.0.0.1:8080 \
  proof-of-audit-web
```

Recommended Artifact Registry image name:

- `proof-of-audit-web`

Like the API image, this image is intended to receive environment tags such as `testnet-candidate` and `mainnet-release` in the release workflow.

## Runtime image release workflow

The repository now includes a single GitHub Actions workflow at `.github/workflows/release-images.yml` to publish all three runtime images expected by the infrastructure repo:

- `proof-of-audit-api`
- `proof-of-audit-web`
- `proof-of-audit-evidence-runner`

The workflow is intentionally explicit about the registry destination. Each manual run requires:

- `gcp_project_id`
- `artifact_registry_region`
- `artifact_registry_repository`
- `release_channel` set to either `testnet-candidate` or `mainnet-release`

Repository auth requirements:

- GitHub secret `GCP_WORKLOAD_IDENTITY_PROVIDER`
- GitHub secret `GCP_SERVICE_ACCOUNT_EMAIL`

Run it from GitHub Actions with the `Release Images` workflow. Each run pushes:

- `${artifact_registry_region}-docker.pkg.dev/${gcp_project_id}/${artifact_registry_repository}/proof-of-audit-api:${release_channel}`
- `${artifact_registry_region}-docker.pkg.dev/${gcp_project_id}/${artifact_registry_repository}/proof-of-audit-web:${release_channel}`
- `${artifact_registry_region}-docker.pkg.dev/${gcp_project_id}/${artifact_registry_repository}/proof-of-audit-evidence-runner:${release_channel}`

When deploying the web image to Cloud Run, configure the service runtime env with `PROOF_OF_AUDIT_API_URL` so the web server can publish the correct public API base URL without rebuilding the image.

This publish step is the application-repo prerequisite for `akoita/proof-of-audit-iac`. Infra bootstrap and Cloud Run deployment expect these environment-tagged images to exist before the `testnet` or `mainnet` services can converge.

For executable evidence hardening, the API can also switch advisory Foundry execution to Docker:

- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_BACKEND`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_IMAGE`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_BIN`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_NETWORK`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_CPUS`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_PIDS_LIMIT`

Recommended Docker backend notes:

- pre-pull and pin a specific Foundry image tag instead of relying on `latest`
- make sure `PROOF_OF_AUDIT_RPC_URL` resolves from inside the container, not only from the host
- the Docker backend mounts validated evidence read-only and writes compiler cache / artifacts only to container tmpfs
- plain local Docker can make network usage explicit with `--network`, but it does not enforce single-endpoint egress policy by itself

For a remote runner deployment, the API can instead switch advisory Foundry execution to Cloud Run:

- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_BACKEND=gcp_cloud_run`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_URL`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_BEARER_TOKEN`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_AUDIENCE`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_GCS_BUCKET`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_GCS_PREFIX`

Recommended Cloud Run backend notes:

- deploy the dedicated runner service from [infra/evidence-runner/cloudbuild.yaml](/home/koita/dev/hackatons/proof-of-audit/infra/evidence-runner/cloudbuild.yaml)
- keep the runner service authenticated by default and grant the API service account `run.invoker`
- if the API runs on GCP, prefer `..._AUDIENCE` over a static bearer token so the backend can mint per-request identity tokens from metadata
- prefer a dedicated staging bucket so the backend can upload the evidence archive to GCS and send the runner only a `gs://` reference
- grant the API service account object create access on the staging bucket and the runner service account object read access
- use lifecycle rules on the staging bucket so uploaded evidence archives expire automatically

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
