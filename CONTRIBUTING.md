# Contributing

Thanks for your interest in improving Proof-of-Audit.

## Development setup

1. Install Python 3.12+, Foundry, Node.js, and pnpm.
2. Run Python tests from the repository root with `make test-python`.
3. Run contract tests with `cd contracts && forge test`.
4. Run the web build with `cd web && pnpm install && pnpm build`.

## Pull request guidelines

- Keep changes focused and easy to review.
- Add or update tests when changing behavior.
- Document user-facing API or workflow changes in `README.md`.
- Avoid committing generated artifacts, local data, or secrets.

## Commit style

- Use clear, descriptive commit messages.
- Prefer small commits that each represent one logical change.

