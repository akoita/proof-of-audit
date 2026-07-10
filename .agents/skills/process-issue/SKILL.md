---
name: process-issue
description: Process a GitHub issue — create branch, implement, commit, PR, merge. Use when asked to "process", "work on", or "implement" a GitHub issue end to end.
---

# Process Issue Workflow

When asked to "process" a GitHub issue, follow these steps exactly:

## 1. Fetch Issue Details
// turbo
```bash
gh issue view <ISSUE_NUMBER> --json title,body,labels,number
```

## 2. Create and Switch to a New Branch
Branch name format: `issue-<NUMBER>-<slug>` where `<slug>` is a short kebab-case summary of the issue title (max 5 words).
// turbo
```bash
git checkout main
git pull origin main
git checkout -b issue-<NUMBER>-<slug>
```

## 3. Implement the Changes
- Read the issue requirements and acceptance criteria carefully
- Implement all required changes
- Run relevant tests to validate

## 4. Commit
// turbo
```bash
git add <files>
git commit -m "<concise title>

<bullet-point summary of changes>"
```

## 5. Push
// turbo
```bash
git push origin issue-<NUMBER>-<slug>
```

## 6. Create PR
// turbo
```bash
gh pr create \
  --base main \
  --head issue-<NUMBER>-<slug> \
  --title "<PR title> (#<ISSUE_NUMBER>)" \
  --body "<PR body with summary, changes, and validation>"
```

## 7. Merge
// turbo
```bash
gh pr merge <PR_NUMBER> --squash --delete-branch \
  --subject "<PR title> (#<PR_NUMBER>)"
```

## 8. Switch Back to Main
// turbo
```bash
git worktree remove /tmp/proof-of-audit-* 2>/dev/null; git checkout main && git pull origin main && git branch -D issue-<NUMBER>-<slug> 2>/dev/null
```

## Notes
- Let the pre-commit security hook run; do not use `--no-verify` (fix failures instead of bypassing)
- The correct Python environment is `pyenv activate proof-of-audit-3.12`
- Run tests with: `PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m pytest agent/tests/ -x -q`
