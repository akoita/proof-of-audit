# Base Sepolia Smoke Evidence - 2026-03-22

## Run target

- Branch: `main`
- Commit: `49043a12df0c727d3914c43cf7de30ebb9a94f2d`
- Workflow: `Testnet Smoke`
- Event: `workflow_dispatch`
- Run URL: https://github.com/akoita/proof-of-audit/actions/runs/23412288593

## Absolute timing

- Started: `2026-03-22T20:54:32Z`
- Finished: `2026-03-22T20:55:21Z`

## Smoke command used

```bash
PYTHON_BIN=python make test-testnet-smoke
```

## Result

The run reported `success` in GitHub Actions, but it did not execute a live Base Sepolia publish/challenge/resolution cycle.

The job log shows the required runtime environment was empty for the smoke step:

- `PROOF_OF_AUDIT_TESTNET_RPC_URL` unset
- `PROOF_OF_AUDIT_TESTNET_PRIVATE_KEY` unset
- `PROOF_OF_AUDIT_TESTNET_API_URL` unset

Pytest collected 4 smoke tests and skipped all 4:

- `api/tests/testnet/test_executable_evidence_smoke.py`
- `api/tests/testnet/test_preflight.py`
- `api/tests/testnet/test_workflow_smoke.py::test_base_sepolia_plain_proof_uri_workflow_stays_open_onchain`
- `api/tests/testnet/test_workflow_smoke.py::test_base_sepolia_manual_resolution_workflow_resolves_onchain`

## Proof artifacts captured

- Publish tx hash: not captured
- Challenge tx hash: not captured
- Resolution tx hash: not captured
- Resulting audit/challenge state: not captured
- Screenshots/JSON excerpts for a live run: not captured

## Assessment

This is not acceptable as final live-evidence proof for judging. It is a green no-op, not a successful live smoke.

## Follow-up in the linked fix

The repo now includes a strict smoke runner and workflow artifact bundle so future runs:

- fail loudly when the live Base Sepolia env is missing
- upload a machine-readable smoke report on every run
- capture structured publish/challenge/resolve artifacts when the env is configured
