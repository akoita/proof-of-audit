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
  --fixture-id clean-vault \
  --typing-speed fast
```

Additional flags:

- `--typing-speed instant|fast|slow` — controls the typewriter effect (default: `fast`)
- `--no-color` — disables ANSI color output
- `--no-sleep` — skips pauses between phases
- `--show-deployment` — displays live Base Sepolia deployment info alongside the demo flow

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
- `TYPING_SPEED` — `instant`, `fast`, or `slow` (default: `fast`)

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

Preview asset:

![Terminal demo poster](./assets/proof-of-audit-agent-demo.svg)

## What the terminal flow shows

The demo runs eight narrative phases, each with colored output, emoji markers, and selective field display:

1. 🔍 **Discover** — `GET /auditor`, `GET /auditor/registration`, `GET /config`
2. 📋 **Select benchmark** — `GET /fixtures`
3. 📝 **Create draft claim** — `POST /audits`
4. ⛓️ **Stake & publish** — `POST /audits/{id}/publish`
5. 🔗 **Validation request** — `GET /audits/{id}/validation/request`
6. ⚔️ **Challenge** — `POST /audits/{id}/challenge`
7. 📄 **Validation response** — `GET /audits/{id}/validation/response`
8. ✅ **Final record** — `GET /audits/{id}`

Each phase highlights:

- the narrative purpose ("Who is the agent? Can I trust it?")
- key fields (agent id, stake, tx hashes, resolution path)
- status badges ("✓ Claim published on-chain")

The story stays focused on:

- agent identity and ERC-8004 discovery
- economic commitment via on-chain stake
- deterministic challenge resolution
- validation interoperability

## Recommended terminal settings

- font size large enough for recording
- terminal width: 120 columns (the recording script sets this automatically)
- terminal height: 36 rows (the recording script sets this automatically)
- clean prompt with minimal shell noise
- dark terminal background for best color contrast

## Notes

- the terminal runner is deterministic for the `clean-vault` fixture
- the browser workbench is not required for this flow
- the cast emphasizes the agent interaction story with narrative commentary
- use `--no-color` if piping output or recording for a light-background context
- use `--typing-speed instant` for CI or automated runs
