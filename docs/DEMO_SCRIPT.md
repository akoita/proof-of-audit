# Demo Script

This script is for a short live walkthrough of the current product.

## Goal

Show one complete trust loop:

1. the auditor is identifiable
2. the auditor makes a claim
3. the claim is published on-chain with stake
4. the claim is challenged with evidence
5. the outcome is resolved on-chain

## Pre-demo setup

For local mode:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/start-anvil.sh
./scripts/deploy-local.sh
./scripts/deploy-demo-fixtures.sh
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m proof_of_audit_api.app
```

In a second terminal:

```bash
cd /home/koita/dev/hackatons/proof-of-audit/web
pnpm dev
```

## 60-second live flow

### 1. Set the context

Open the workbench and point to:

- the named auditor identity
- the service-discovery record
- the active chain configuration

Say:

> This is not just an audit UI. It is infrastructure that lets a named agent publish a stake-backed code judgment that others can challenge on-chain.

### 2. Generate a claim

Use the `Clean Vault` fixture.

Why:

- it cleanly demonstrates the strongest deterministic challenge path
- the initial claim is “no benchmark issue found”
- the later challenge is easy to understand

Click:

- `Generate claim`

Say:

> The auditor creates a review claim first. At this stage it is only a draft.

### 3. Publish on-chain

Click:

- `Stake and publish`

Point to:

- audit id
- publish transaction
- stake amount

Say:

> Now the agent is economically committed to its judgment. The claim is visible and portable because it is recorded on-chain.

### 4. Challenge with curated evidence

Leave the suggested `clean-vault` proof URI in place and click:

- `Open challenge`

Point to:

- `Deterministic path`
- challenge tx
- resolution tx
- final resolution status

Say:

> The challenge uses curated evidence for a known benchmark case, so the verifier resolves it automatically on-chain. Human review is only the fallback path for ambiguous evidence.

### 5. Close with the trust model

Say:

> The important part is not that the system generated a judgment. The important part is that the judgment became stake-backed, challengeable, and transparently enforceable.

## Backup flow

If the UI is unavailable:

1. show `/config`
2. show `/auditor`
3. create an audit via `POST /audits`
4. publish via `POST /audits/:id/publish`
5. challenge via `POST /audits/:id/challenge`

Those endpoints expose the same story without relying on the browser.
