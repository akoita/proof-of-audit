# Judge Evaluation Path

## Recommended path

Use the local one-command stack. There is not yet a stable public web/API deployment for evaluation, so this is the default path for judges.

## One command

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/run-judge-stack.sh
```

The script:

- starts Anvil on `http://127.0.0.1:8545`
- deploys the local demo contract set
- starts the API on `http://127.0.0.1:8080`
- starts the web app on `http://127.0.0.1:3000`
- waits for the stack to become healthy before printing the URLs

Keep that terminal open while you evaluate the project.

## What to open

- Primary path: `http://127.0.0.1:3000`
- Fallback API docs: `http://127.0.0.1:8080/docs`

## What to try

1. Open the workbench and inspect the configured Base Sepolia metadata.
2. Select the `Clean Vault` fixture and run an audit.
3. Publish the claim on the local chain.
4. Challenge the claim and inspect the challenge record.
5. If needed, inspect the fallback API docs directly.

## Why this is the recommended path

- it is one command
- it uses the same health-checked stack boot path exercised by the repo's UI automation
- it avoids depending on an unpublished public API host
- it shows the full user-facing web and API flow without extra setup docs
