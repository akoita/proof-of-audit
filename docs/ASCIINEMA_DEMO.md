# Asciinema Demo

This runbook captures the terminal-first Proof-of-Audit flow for agent callers.

The goal is to show one complete loop without using the browser workbench:

1. discover the auditor service
2. inspect the ERC-8004-aligned registration
3. create a draft claim
4. publish the claim on-chain
5. challenge it with deterministic evidence
6. inspect the validation trail

## Prerequisites

- local Anvil stack running
- local API running on `http://127.0.0.1:8080`
- `asciinema` installed if you want to record a cast

Local stack setup:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/start-anvil.sh
./scripts/prepare-agent-demo-stack.sh
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m proof_of_audit_api.app
```

`./scripts/prepare-agent-demo-stack.sh` bootstraps all local pieces needed by the terminal recording:

- `ProofOfAudit`
- demo fixtures
- local fallback `AgentIdentityRegistry`
- local `ValidationRegistryAdapter`
- generated `api/.env.local` values for agent identity and validation bridge settings

## Dry-run the terminal demo

Run the terminal flow without recording first:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
/home/koita/.pyenv/versions/proof-of-audit-3.12/bin/python \
  ./scripts/run_agent_demo.py \
  --api-url http://127.0.0.1:8080 \
  --fixture-id clean-vault
```

Recommended fixture:

- `clean-vault`

Why:

- it demonstrates the strongest deterministic challenge path
- the validation response becomes available immediately after the challenge flow

## Record the cast

```bash
cd /home/koita/dev/hackatons/proof-of-audit
PYTHON_BIN=/home/koita/.pyenv/versions/proof-of-audit-3.12/bin/python \
  ./scripts/record-agent-demo.sh
```

Default output:

- `/home/koita/dev/hackatons/proof-of-audit/docs/assets/proof-of-audit-agent-demo.cast`

Useful environment overrides:

- `PROOF_OF_AUDIT_API_URL`
- `FIXTURE_ID`
- `CAST_PATH`
- `TITLE`
- `IDLE_LIMIT`

## Publish to Asciinema

If you want the recorder to upload immediately after capture:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
ASCIINEMA_UPLOAD=1 \
PYTHON_BIN=/home/koita/.pyenv/versions/proof-of-audit-3.12/bin/python \
  ./scripts/record-agent-demo.sh
```

Or upload later:

```bash
asciinema upload /home/koita/dev/hackatons/proof-of-audit/docs/assets/proof-of-audit-agent-demo.cast
```

Published recording:

- current upload: [asciinema.org/a/5u5so0LWHCE6J4dC](https://asciinema.org/a/5u5so0LWHCE6J4dC)
- note: this upload was created from an unauthenticated CLI session, so Asciinema marks it for automatic deletion after 7 days unless it is re-uploaded from an authenticated machine

## What the terminal flow shows

The demo runner hits these endpoints in order:

- `GET /auditor`
- `GET /auditor/registration`
- `GET /config`
- `GET /fixtures`
- `POST /audits`
- `POST /audits/{id}/publish`
- `GET /audits/{id}/validation/request`
- `POST /audits/{id}/challenge`
- `GET /audits/{id}/validation/response`
- `GET /audits/{id}`

That keeps the story focused on:

- agent identity
- ERC-8004 discovery and registration
- native on-chain settlement
- validation interoperability

## Recommended terminal settings

- font size large enough for recording
- terminal width around 100 columns
- terminal height around 32 rows
- clean prompt with minimal shell noise

## Notes

- the terminal runner is deterministic for the `clean-vault` fixture
- the browser workbench is not required for this flow
- the cast should emphasize the API and identity story, not local setup commands
