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

## Bundle version

Current manifest version:

- `proof-of-audit-executable-evidence/v1`

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

This allows later issues to add:

- canonical on-chain bundle hash commitments

without redefining the bundle shape again.
