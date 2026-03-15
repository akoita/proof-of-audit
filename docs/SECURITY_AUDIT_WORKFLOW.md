# Security Audit Workflow

Proof-of-Audit includes a local pre-commit security audit gate for staged Solidity and security-sensitive backend changes.

## Goals

- run extra security-focused checks only when the staged diff justifies them
- keep the workflow local and predictable
- rely on a short list of trusted sources instead of arbitrary marketplace installs

## Install

Run this once per clone:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
make install-git-hooks
```

That sets `core.hooksPath` to `.githooks`, so the repository-local `pre-commit` hook becomes active.

## What the hook does

The hook inspects staged files with:

```bash
git diff --cached --name-only --diff-filter=ACMR
```

Then it classifies the diff into two trigger buckets.

### Solidity-sensitive changes

Triggered by staged files under:

- `contracts/**/*.sol`
- `demo/contracts/**/*.sol`

Command:

```bash
forge test --root contracts
```

### Backend-sensitive changes

Triggered by staged files under:

- `api/proof_of_audit_api/**`
- `agent/proof_of_audit_agent/**`
- `scripts/deploy-*`
- `scripts/verify-*`
- `scripts/write-*`
- `.env.example`
- `pyproject.toml`

Command:

```bash
PYTHONPATH=agent:api python -m pytest \
  agent/tests/test_worker.py \
  api/tests/test_app.py \
  api/tests/test_service.py \
  api/tests/test_submission_modes.py \
  api/tests/test_config.py \
  api/tests/test_erc8004_registration.py \
  -q
```

## Manual usage

You can run the same workflow before committing:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
PYTHON_BIN=/home/koita/.pyenv/versions/proof-of-audit-3.12/bin/python \
  ./scripts/run-pre-commit-security-audit.sh
```

Or preview the plan for a specific file set without running commands:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
/home/koita/.pyenv/versions/proof-of-audit-3.12/bin/python \
  ./scripts/run_pre_commit_security_audit.py \
  --files contracts/src/ProofOfAudit.sol api/proof_of_audit_api/service.py \
  --skip-commands \
  --plan-json
```

The workflow writes a local report to `.tmp/security-audit/pre-commit-report.md`.

## Trusted source policy

This workflow is intentionally conservative. It does not auto-install plugins from arbitrary registries.

Approved reference sources for extending the audit gate:

- [OpenZeppelin Skills](https://github.com/OpenZeppelin/openzeppelin-skills)
- [Pashov Skills](https://github.com/pashov/skills)
- [Trail of Bits Curated Skills](https://github.com/trailofbits/skills-curated)

These sources inform how the trigger map and review focus should evolve over time, especially for Solidity and security-review tasks.

## Extending the workflow

When adding a new trigger:

1. document the file pattern and why it is security-sensitive
2. keep the command local-first and deterministic
3. prefer source-controlled scripts over downloaded plugins
4. update tests for `scripts/run_pre_commit_security_audit.py`

The gate is meant to increase confidence before commits without turning every small change into a full security review ceremony.
