# Contributing

## Contribution policy

External contributions remain paused during the vision reset. Open issues are
the maintainer's working backlog, not an invitation to submit implementation
pull requests. Comment on an issue or open a discussion and obtain an explicit
go-ahead before writing code. Unsolicited pull requests will be closed without
detailed review, including automated submissions.

Authorized work must align with the [vision](./docs/strategy/VISION.md) and
[current roadmap phase](./docs/strategy/ROADMAP.md). Preserve local changes and
never commit runtime data, secrets, or deployment overrides.

## Development setup

Install Python 3.12+ through pyenv, Foundry, Node.js, and pnpm. The maintainer's
Python environment is named `proof-of-audit-3.12`; create or select that
environment before using the commands below. Run commands from the repository
root unless a block explicitly changes directory.

```bash
export PYENV_VERSION=proof-of-audit-3.12
export PYTHONPATH=agent:api
python -m pip install setuptools wheel
python -m pip install --no-build-isolation -e '.[dev]'
make install-git-hooks
```

Install frontend dependencies in a separate shell or return to the repository
root afterward:

```bash
cd web
pnpm install --frozen-lockfile
pnpm build
```

Use the [README walkthrough](./README.md#try-the-local-fixture-workflow) to start
the fixture stack. Use [deployment](./docs/DEPLOYMENT.md) for configuration and
[Local Agent Forge](./docs/LOCAL_AGENT_FORGE.md) for live engine integration.

## Verification

Run the required Python suite before committing:

```bash
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api \
  python -m pytest agent/tests/ api/tests/ -x -q \
  --ignore=agent/tests/test_executable_evidence_resolver.py
```

The excluded resolver module requires its separate Foundry setup under the
repository instructions. Live testnet tests require explicit configuration;
skips do not prove that a deployment works. Additional checks depend on the change:

| Change or verification goal | Command from the repository root |
| --- | --- |
| Solidity build and tests | `forge build --root contracts` and `make test-contracts` |
| Symbolic contract properties | `make test-formal` |
| API/chain integration | `PYENV_VERSION=proof-of-audit-3.12 make test-system-e2e PYTHON=python` |
| Browser workflow | `PYENV_VERSION=proof-of-audit-3.12 make test-ui-e2e PYTHON=python` |
| Configured Base Sepolia stack | `PYENV_VERSION=proof-of-audit-3.12 make test-testnet-smoke PYTHON=python` |

See [formal testing](./docs/FORMAL_TESTING.md) for tool versions and
[technical test layers](./docs/TECHNICAL_DOCUMENTATION.md#test-layers) for scope.
When test environments disagree, first check ignored local configuration and
registry/deployment addresses; do not bypass failed checks.

## Security hook

`make install-git-hooks` installs the pre-commit gate. It resolves the project
Python environment and checks staged security-sensitive changes. Never use
`--no-verify`. To run the gate manually after staging:

```bash
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api \
  make security-audit-staged PYTHON=python
```

The report is written to `.tmp/security-audit/pre-commit-report.md`. Review the
[security audit workflow](./docs/SECURITY_AUDIT_WORKFLOW.md) for triggers and
commands. The gate complements the required test suite; it does not replace it.

## Branches and pull requests

Follow [AGENTS.md](./AGENTS.md) for branch conventions: `issue-<number>-<slug>`
for issue work, `feat/<slug>` for untracked features, and `fix/<slug>` for
untracked fixes. The existing `start-issue-branch.sh` helper creates a legacy
`codex/...` name; use an explicit branch name to follow the current convention.

Work from a feature branch, add focused changes and relevant tests, update the
affected documentation, and submit a pull request targeting `main`. Reference
the issue when applicable. Obtain approval before committing or pushing under
the repository completion workflow. Merge only after CI passes and the
maintainer explicitly requests it. Never push directly to `main`.

After merge, delete the feature branch locally and remotely and align local
`main` with the remote. Use the repository's `process-issue` and `finish-issue`
skills for the applicable workflow.

## Documentation maintenance

Use [docs/README.md](./docs/README.md) to find the authoritative document for a
subject. Keep current behavior separate from draft designs, planned work, and
historical records. Update living guides alongside behavior changes; do not
turn a proposal into a current-state claim before delivery.

Use repository-relative Markdown links and portable commands. Preserve familiar
paths or leave a compatibility entry when moving externally referenced material.
Check local links and heading anchors, referenced commands/configuration, and
paragraph structure before submitting. Add a decision record only when a
consequential decision has actually been made; supersede accepted records
rather than rewriting their history.
