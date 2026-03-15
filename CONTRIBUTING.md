# Contributing

Thanks for your interest in improving Proof-of-Audit.

## Development setup

1. Install Python 3.12+, Foundry, Node.js, and pnpm.
2. Install Python dependencies with `python3 -m pip install setuptools wheel && python3 -m pip install --no-build-isolation -e '.[dev]'`.
3. Run Python tests from the repository root with `make test-python`.
4. Run contract tests with `cd contracts && forge test`.
5. Run the web build with `cd web && pnpm install && pnpm build`.

## Pre-commit security audit workflow

Install the repository git hooks once per clone:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
make install-git-hooks
```

After that, commits automatically run the changed-files security audit gate when staged files touch:

- Solidity contracts under `contracts/` or `demo/contracts/`
- security-sensitive backend code under `api/proof_of_audit_api/`, `agent/proof_of_audit_agent/`, and release/deploy scripts

You can run the same gate manually before committing:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
PYTHON=/home/koita/.pyenv/versions/proof-of-audit-3.12/bin/python make security-audit-staged
```

The hook writes a local report to `.tmp/security-audit/pre-commit-report.md` and only blocks commits when the relevant audit commands fail. See [Security audit workflow](/home/koita/dev/hackatons/proof-of-audit/docs/SECURITY_AUDIT_WORKFLOW.md) for the trigger map and trusted source policy.

## Issue-driven workflow

Work should start from a GitHub issue that is already assigned to a roadmap phase.

1. Pick or assign a GitHub issue.
2. Create a task branch from `main`.
3. Implement the change with focused commits.
4. Push the branch and open a pull request.
5. Wait for CI to pass before merge.
6. Merge the pull request.
7. Delete the task branch after merge.

### Branch naming

Use the repository branch convention:

- `codex/feature/<issue-number>-<short-slug>`
- `codex/fix/<issue-number>-<short-slug>`
- `codex/chore/<issue-number>-<short-slug>`

Example:

```bash
git checkout main
git pull --ff-only
./scripts/start-issue-branch.sh 8 feature fastapi-migration
```

## Pull request guidelines

- Keep changes focused and easy to review.
- Add or update tests when changing behavior.
- Document user-facing API or workflow changes in `README.md`.
- Avoid committing generated artifacts, local data, or secrets.
- Reference the related GitHub issue in the pull request description.
- Do not merge until CI is green.

## Commit style

- Use clear, descriptive commit messages.
- Prefer small commits that each represent one logical change.

## Merge and cleanup

After a pull request is merged:

1. delete the remote branch
2. delete the local task branch
3. return to `main` and pull the latest changes
