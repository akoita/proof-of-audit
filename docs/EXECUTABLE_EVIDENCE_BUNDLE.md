# Executable Evidence Bundle Format

This note defines the current bundle shape for executable challenge evidence.

It is the format companion for the advisory executable verifier introduced in:

- [/home/koita/dev/hackatons/proof-of-audit/docs/AGENT_API.md](/home/koita/dev/hackatons/proof-of-audit/docs/AGENT_API.md)

## Status

Current status: format defined and advisory bundle execution implemented.

That means:

- the API can carry manifest-shaped metadata for executable evidence
- the advisory runner can fetch and validate remote evidence into a temp directory before execution
- validated bundles can be executed from an isolated temp root with manifest-driven entrypoint selection
- the API host can optionally execute advisory Foundry evidence in a hardened local Docker container instead of directly on the host subprocess path
- the API host can also offload advisory Foundry execution to a dedicated Cloud Run runner service when stronger host separation or separate scaling is needed

## Bundle version

Current manifest version:

- `proof-of-audit-executable-evidence/v1`

Canonical evidence hash version:

- `proof-of-audit-executable-evidence-hash/v1`

## Intended bundle layout

An executable evidence bundle is intended to contain:

1. `manifest.json`
2. one entry test file
3. optional helper contracts
4. optional metadata files

Example shape:

```text
challenge-bundle/
  manifest.json
  test/ChallengeEvidence.t.sol
  src/Helper.sol
  README.md
```

## Manifest fields

Required fields:

- `bundle_format`
  - current value: `proof-of-audit-executable-evidence/v1`
- `execution_env`
  - current MVP value: `foundry`
- `entrypoint`
  - bundle-relative path to the entry test file
- `target_chain_id`
  - chain id the evidence expects to run against

Optional fields:

- `test_contract`
  - explicit Foundry test contract name
- `match_contract`
  - alternative contract selector when `test_contract` is not provided
- `pinned_block_number`
  - explicit fork block to use for deterministic replay
- `expected_file_hashes`
  - map of bundle-relative path to `sha256` hex digest
- `metadata_path`
  - bundle-relative path to extra metadata or notes

## Canonical hashing rules

For executable challenge commitments, the committed on-chain hash is not `sha256(proof_uri)`.

Instead, the API computes a canonical evidence hash from the validated materialized evidence:

1. resolve and validate the evidence source
2. normalize the bundle root
3. collect the bundle-relative entrypoint path
4. collect `sha256` digests for the included files
5. hash a canonical JSON payload containing:
   - canonical hash format version
   - bundle mode flag
   - entrypoint
   - normalized manifest payload
   - sorted file digest map

For single-file executable evidence, the file digest map contains only the submitted Solidity test file.

For validated bundles, the file digest map contains every regular file under the normalized bundle root.

The resulting digest is committed on-chain as `evidenceHash`.

Constraint:

- `test_contract` and `match_contract` are mutually exclusive

## Example manifest

```json
{
  "bundle_format": "proof-of-audit-executable-evidence/v1",
  "execution_env": "foundry",
  "entrypoint": "test/ChallengeEvidence.t.sol",
  "target_chain_id": 84532,
  "test_contract": "ChallengeEvidenceTest",
  "pinned_block_number": 28900000,
  "expected_file_hashes": {
    "test/ChallengeEvidence.t.sol": "5a9c3a...",
    "src/Helper.sol": "86f812..."
  },
  "metadata_path": "README.md"
}
```

## Current MVP behavior

The current MVP is intentionally narrower than the full bundle format.

Supported today:

- executable evidence request may include manifest-shaped metadata
- executable evidence may be provided through:
  - absolute local path
  - `file://`
  - `ipfs://`
  - `http://`
  - `https://`
- the advisory runner can use:
  - `execution_env`
  - `target_chain_id`
  - `pinned_block_number`
- validated bundles can execute with:
  - manifest `entrypoint`
  - wrapped archive root normalization for single-directory bundles
  - helper contracts included under the bundle root
  - optional `test_contract` or `match_contract` selector
- the runner validates and materializes remote evidence before execution
- archive extraction is guarded by size, file-count, path, symlink, and extension checks
- executable challenges commit a canonical `evidenceHash` on-chain instead of only hashing the locator URI
- the advisory runner re-hashes fetched executable evidence and rejects execution if it no longer matches the committed hash
- deployments can switch the advisory runner from `local_subprocess` to `docker` with environment configuration
- deployments can also switch the advisory runner to `gcp_cloud_run` with a dedicated runner service URL and auth configuration

Not supported yet:

- canonical on-chain evidence bundle hashes
- bundle-provided `foundry.toml`, remappings, or custom dependency resolution outside the validated bundle root

## Backward compatibility

The current single-file executable evidence path remains valid.

If a caller only has one Solidity test file, it may continue to submit:

- `proof_uri`
- `evidence_type = "executable_test"`
- `execution_env = "foundry"`

The manifest is optional for that path.

If a manifest is supplied during the single-file MVP, it should describe that same file as the `entrypoint`.

If the evidence is supplied as a remote archive, callers should include `manifest.json` in the bundle or provide equivalent manifest metadata in the request.

## API relationship

For executable evidence, the API now treats the manifest as the canonical description of execution intent.

The request still carries `proof_uri`, but the manifest is where callers should specify:

- execution environment
- target chain
- entrypoint
- optional pinned block

The challenge record distinguishes:

- `proof_uri`
  - locator for where evidence was fetched
- `evidence_hash`
  - canonical content hash committed on-chain for executable evidence

This allows later issues to add:

- canonical on-chain bundle hash commitments

without redefining the bundle shape again.

## Execution backend configuration

The advisory runner defaults to the local subprocess backend.

To use the hardened local Docker backend instead, configure:

- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_BACKEND=docker`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_IMAGE=<foundry-image>`

Optional Docker backend overrides:

- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_BIN`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_NETWORK`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_CPUS`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_PIDS_LIMIT`

The Docker backend mounts the validated evidence root read-only at `/evidence`, uses a writable tmpfs at `/tmp` for cache and artifact output, drops all Linux capabilities, and disables new privileges.

To use the Cloud Run backend instead, configure:

- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_BACKEND=gcp_cloud_run`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_URL=<runner-service-url>`

Cloud Run auth options:

- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_BEARER_TOKEN`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_AUDIENCE`
- `PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED=1`

If `..._AUDIENCE` is configured, the backend fetches an identity token from the GCP metadata server before calling the runner service. That is the intended path when the API itself runs on GCP with a service account allowed to invoke the Cloud Run runner.
