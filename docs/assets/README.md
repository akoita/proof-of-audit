# Demo Assets

This folder contains the current demo screenshots used for the public alpha docs.

It also holds generated terminal demo recordings when available, including:

- `proof-of-audit-agent-demo.cast`
- `proof-of-audit-agent-demo.svg`

Generated screenshots:

- `workbench-overview.png`
- `workbench-draft-claim.png`
- `workbench-challenge-resolution.png`

Refresh them with:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
zsh -lic './scripts/capture-demo-assets.sh'
```

The capture flow boots the local demo stack, opens the workbench, and records the main publish, challenge, and resolution path.

The terminal SVG is generated from the `.cast` file via `svg-term-cli` and is embedded in the README as an animated preview.
