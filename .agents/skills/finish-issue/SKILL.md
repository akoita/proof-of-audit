---
name: finish-issue
description: Finish working on a GitHub issue — verify, test, commit, push, PR, merge, and clean up branches. Use when asked to "finish issue", "close issue", "wrap up", or finalize the current branch.
---

When the user says "finish issue", "close issue", "wrap up", or wants to finalize work on the current branch, follow these steps.

> **No-issue mode**: This workflow can be invoked without a linked GitHub issue. When there is no issue, skip all issue-dependent operations (fetching issue details, referencing `#N` in commits/PR, `Closes #N` in PR body, issue-number-based branch naming). Everything else applies normally.

## 1. Verify the branch
// turbo

- Run `git branch --show-current` to check the current branch
- If on `main`, identify the feature branch for the issue and switch to it
- If no feature branch exists, create one following the convention: `issue-<NUMBER>-<short-kebab-description>`
  // turbo
- Run `git status` to see uncommitted changes

## 2. Verify implementation coverage
- **If an issue exists:** Fetch the issue details from GitHub using `gh issue view <NUMBER> --json title,body,labels,number` (owner: `akoita`, repo: `proof-of-audit`), re-read the acceptance criteria and scope, and review every modified/added file against the issue requirements. If anything is missing, implement it before proceeding.
- **If no issue:** Review the modified/added files to confirm the intended change is complete.

## 3. Ensure test coverage
- Identify all changed and new files: `git diff --name-only main`
- For each changed component/module, check if automated tests exist
- If tests are missing or outdated, create or update them
- Test files should follow the project's existing test conventions:
  - Agent tests: `agent/tests/test_*.py`
  - API tests: `api/tests/test_*.py`

## 4. Run tests
// turbo
```bash
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m pytest agent/tests/ api/tests/ -x -q --ignore=agent/tests/test_executable_evidence_resolver.py
```
- If any tests fail, fix the code or tests and re-run
- Do NOT proceed until all tests pass

## 5. Run contract tests (if applicable)
Check the changed files (`git diff --name-only main`):

- **If `contracts/` files changed:**
  ```bash
  cd contracts && forge build && forge test
  ```
  Fix any failures before proceeding.
- **If no contract files changed**, skip this step.

## 6. Update documentation
- Check if the change affects any existing docs (READMEs, docs/, specs, API docs)
- If so, update them in the same branch — keep docs close to the code they describe
- For new features or architectural changes, add documentation in the appropriate location:
  - `docs/` for project-level documentation (challenger feed, deployment guides, etc.)
  - `docs/registrations/` for agent registration documents
  - Inline docstrings for Python modules and functions
  - NatSpec comments for Solidity contracts
- Update `.env.example` if any new environment variables were introduced
- Skip this step if the change is trivial or purely internal refactoring

## 7. Update architecture docs
- Think about whether this change introduces or modifies **architectural patterns** — new agent modules, data flows, contract interactions, cross-agent workflows, etc.
- If the architecture has evolved:
  - Search for **all related architecture docs** in `docs/`, `README.md`, and any diagrams
  - Update them in-place to reflect the new state — keep diagrams, flow descriptions, and component lists current
  - If no existing doc covers the new architecture area, **create a new doc** in `docs/` with:
    - High-level overview and motivation
    - Component diagram (Mermaid preferred)
    - Data flow / sequence diagram for key operations
    - Key design decisions and trade-offs
- Update `AGENTS.md` project structure section if new top-level modules or scripts were added
- Skip this step if the change is purely internal refactoring with no architectural impact

## 8. Clean commit(s)
- Review staged/unstaged changes: `git diff --cached` and `git diff`
- **Security check** — make sure NONE of these are committed:
  - `.env` files, API keys, secrets, tokens, private keys
  - **Hardcoded credentials in ANY file** (e.g. passwords, API keys, wallet private keys embedded in source code, config files, scripts, Terraform tfvars, or Docker compose files)
  - Large binary files, `node_modules/`, build artifacts, `__pycache__/`
  - Database dumps, logs, local config overrides, `api/data/`
- Check `.gitignore` covers suspicious files: `git status --ignored`
- If any sensitive files are tracked, add them to `.gitignore` first
- Make atomic, well-scoped commits with `--no-verify`:
  - **With issue:** `feat(#N): description` or `fix(#N): description`
  - **Without issue:** `feat: description` or `fix: description`
  - One logical change per commit — split if needed

## 9. Push the branch
// turbo

- Push to remote: `git push -u origin <branch-name>`
- Verify the push succeeded

## 10. Create PR and merge
- Create a Pull Request targeting `main` with:
  - Title: concise description (referencing the issue number if one exists)
  - Body: summary of changes (+ `Closes #N` only if an issue exists)
// turbo
```bash
gh pr create \
  --base main \
  --head <branch-name> \
  --title "<PR title> (#<ISSUE_NUMBER>)" \
  --body "<PR body>"
```
- Merge the PR (prefer squash merge for clean history)
// turbo
```bash
gh pr merge <PR_NUMBER> --squash --delete-branch
```

## 11. Clean up and align main
// turbo
```bash
git checkout main && git pull origin main
```
// turbo
- Verify alignment: `git log --oneline -5`
- Delete any leftover local branches: `git branch -D <branch-name> 2>/dev/null`

## Important rules
- **NEVER push a file that contains clear private data** — no hardcoded credentials, API keys, passwords, private keys, or tokens in ANY file, regardless of file type. Scan every file before staging.
- **NEVER commit or push before user approval** — always ask first
- **NEVER force-push to `main`**
- **NEVER delete `main`** — only delete feature and fix branches
- **Always use `--no-verify`** on commit — the pre-commit hook uses the wrong Python version
- If in doubt about sensitive files, ask the user before committing
- If the merge creates conflicts, resolve them on the feature branch before merging
